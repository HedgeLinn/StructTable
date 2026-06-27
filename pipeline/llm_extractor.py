"""
LLM-based extraction — sends HTML table to model API, auto-detects structure.

Handles:
  - Multi-table sections (splits + merge continuation groups)
  - Large tables (token estimation + auto-split)
  - Orphan detail items (post-process reattachment to parent IDs)
  - Monitoring: tracks parse failures, orphan counts, ID gaps per section
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from .utils import read_file, write_json, validate_all, print_validation_report


# ═══════════════════════════════════════════════════════════════
# Prompt
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是一个 HTML 表格结构化提取专家。观察 HTML 表格，自动发现数据结构，转换为 JSON。

## 核心规则

1. **每个输出对象必须包含编号字段** — 定额编号 / 清单编码 / 指标编号 / 清单编号 等。没有编号的行不得作为独立顶层条目输出。
2. **明细项必须嵌套** — 名称、单位、单价、数量 的明细行，必须嵌套在父级对象的 人工/材料/机械 数组内。
3. **一个对象 = 一个编号 × 一个规格** — 横向多列规格值 → 每列拆成独立对象。
4. **字段名使用表格中实际出现的标签文字** — 不要自己发明字段名。

## 结构发现

- 编号列：找到「定额编号」「清单编码」「指标编号」「清单编号」，值如 1-1、H-001
- 规格列：DN300/DN400 或纯数字 → 加 DN 前缀
- 基价/费用行：提取「基价」及「人工费」「材料费」「机械费」后的数值
- 明细段：「名称」「单位」「单价」开头的区域，后面是数量列

## 输出示例

定额表（有费用构成）：
```json
[{
  "定额编号": "1-1",
  "项目名称": "xxx", "工作内容": "xxx",
  "规格": "DN400", "计量单位": "台",
  "基价": 819864.56,
  "费用构成": {"人工费": 527236.94, "材料费": 145572.61, "机械费": 147055.01},
  "人工": [{"名称": "综合工日", "单位": "工日", "单价": 183.86, "数量": 2867.6}],
  "材料": [...], "机械": [...]
}]
```

全费用清单（扁平列）：
```json
[{"清单编码": "050101001", "清单名称": "xxx", "项目名称": "xxx", "规格": "DN300", "计量单位": "处", "清单单价": 1341.0, "规费": 0, "安全文明施工费": 0}]
```

多区域定价：
```json
[{"指标编号": "H-001", "项目名称": "xxx", "管径范围": "DN400", "深度": "2", "定价": [{"区域": "华东地区", "单价": 10848.0}]}]
```

## 数值规则
- (0.200) 或 （0.200）→ -0.200
- 保持原始精度，空值用 0

## 输出
- 纯 JSON 数组，无 markdown 包裹，无解释文字
"""

USER_PROMPT_TEMPLATE = """请将以下 HTML 表格转换为结构化 JSON 数组。

上下文：{chapter} / {h2} {h3}
工作内容：{work_content}
计量单位：{unit}

注意：
- 表格有定额编号行 → 每个编号×规格生成独立对象
- 表格无定额编号行 → 这是续表，明细归入上文最近的编号
- 明细项（名称/单位/单价/数量）必须嵌套，不得独立输出

HTML：
{html_table}"""


# ═══════════════════════════════════════════════════════════════
# LLM Client
# ═══════════════════════════════════════════════════════════════

class LLMClient:
    def __init__(self, api_url: str, api_key: str, model: str = "deepseek-v4-pro",
                 temperature: float = 0.0, max_tokens: int = 8192,
                 timeout: int = 180, max_retries: int = 2):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries

    def chat(self, system: str, user: str) -> str | None:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self.temperature, "max_tokens": self.max_tokens,
        }
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(self.api_url, headers=headers, json=payload, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except requests.Timeout:
                last_error = f"Timeout ({self.timeout}s)"
            except Exception as e:
                last_error = str(e)
            if attempt < self.max_retries:
                wait = (attempt + 1) * 5
                print(f"  [LLM Retry {attempt+1}/{self.max_retries}] {last_error}, waiting {wait}s...")
                time.sleep(wait)
        print(f"  [LLM Error] {last_error}")
        return None


# ═══════════════════════════════════════════════════════════════
# Token estimation
# ═══════════════════════════════════════════════════════════════

def _estimate_tokens(text: str) -> int:
    """Rough token count: ~1 token per 2.5 chars for Chinese (conservative)."""
    return max(1, len(text) // 2)


def _split_large_html(html: str, max_chars: int = 25000) -> list[str]:
    """Split oversized HTML into chunks at table boundaries.
    Falls back to row-level splitting for single giant tables.
    """
    if len(html) <= max_chars:
        return [html]

    tables = re.findall(r'(<table\b[^>]*>.*?</table>)', html, re.DOTALL)
    if not tables:
        return [html]

    chunks = []
    current = ""
    for tbl in tables:
        if len(current) + len(tbl) > max_chars and current:
            chunks.append(current)
            current = tbl
        else:
            current += ("\n" + tbl) if current else tbl
    if current:
        chunks.append(current)

    # If a single table still exceeds limit, split by <tr> groups
    final = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            final.append(chunk)
            continue
        rows = re.findall(r'(<tr\b[^>]*>.*?</tr>)', chunk, re.DOTALL)
        sub = ""
        for row in rows:
            if len(sub) + len(row) > max_chars and sub:
                # Wrap in a minimal <table> for valid HTML
                final.append(f'<table>{sub}</table>')
                sub = row
            else:
                sub += row
        if sub:
            final.append(f'<table>{sub}</table>')

    return final


# ═══════════════════════════════════════════════════════════════
# Post-process: reattach orphan detail items to parent entries
# ═══════════════════════════════════════════════════════════════

_ID_FIELDS = {'定额编号', '清单编码', '清单编号', '指标编号', '序号'}
_DETAIL_KEYS = {'名称', '单位', '单价', '数量'}


def _post_process(items: list[dict]) -> dict:
    """Reattach orphan detail items to their parent entries.

    Returns: {"fixed": list[dict], "stats": dict}
    """
    stats = {"orphans_found": 0, "orphans_reattached": 0, "orphans_dropped": 0}

    if not items:
        return {"fixed": items, "stats": stats}

    # Split into parents (have ID) and candidates (no ID)
    parents = []
    orphans = []
    parent_ids = []
    for item in items:
        clean_keys = {k for k in item if not k.startswith('_')}
        has_id = bool(_ID_FIELDS & clean_keys)
        has_detail = bool(_DETAIL_KEYS & clean_keys)

        if has_id:
            parents.append(item)
            pid = next(iter(_ID_FIELDS & clean_keys), '?')
            parent_ids.append(f"{pid}={item.get(pid, '?')}")
        elif has_detail and len(clean_keys) >= 3:
            orphans.append(item)
        else:
            parents.append(item)

    if not orphans:
        return {"fixed": items, "stats": stats}

    print(f"  [PostProcess] {len(parents)} parents ({parent_ids[:5]}...), "
          f"{len(orphans)} orphans")

    stats["orphans_found"] = len(orphans)

    # Try to reattach each orphan to the nearest preceding parent
    for orphan in orphans:
        name = orphan.get('名称', '')
        unit = orphan.get('单位', '')
        price = orphan.get('单价', 0)
        qty = orphan.get('数量', 0)

        # Find nearest parent with same _source context
        orphan_src = orphan.get('_source', {})
        best_parent = None
        for p in reversed(parents):
            p_src = p.get('_source', {})
            if p_src.get('h2') == orphan_src.get('h2'):
                best_parent = p
                break

        if best_parent is None and parents:
            best_parent = parents[-1]  # fallback to last parent

        if best_parent is None:
            stats["orphans_dropped"] += 1
            continue

        # Determine category: 人工, 材料, or 机械
        category = '材料'
        if unit == '工日' or name.startswith('综合工日'):
            category = '人工'
        elif unit == '台班':
            category = '机械'

        # Add to parent
        if category not in best_parent:
            best_parent[category] = []
        best_parent[category].append({
            '名称': name,
            '单位': unit,
            '单价': price if isinstance(price, (int, float)) else 0,
            '数量': qty if isinstance(qty, (int, float)) else 0,
        })
        stats["orphans_reattached"] += 1

    # Return parents only (orphans are now nested)
    fixed = parents
    return {"fixed": fixed, "stats": stats}


# ═══════════════════════════════════════════════════════════════
# LLM Extractor
# ═══════════════════════════════════════════════════════════════

class LLMExtractor:

    MAX_CHARS_PER_CALL = 25000  # ~12.5k tokens, well under 8k output limit

    def __init__(self, client: LLMClient, workers: int = 5):
        self.client = client
        self.workers = workers
        self.monitor = {"total_sections": 0, "skipped": 0, "parse_errors": 0,
                        "empty_responses": 0, "orphans_reattached": 0,
                        "chunks_split": 0, "llm_errors": 0}

    def extract(self, sections: list[dict]) -> list[dict]:
        """Extract from all sections. Returns combined + post-processed items."""
        self.monitor["total_sections"] = len(sections)

        tasks = []
        for i, sec in enumerate(sections):
            html = sec.get("html_table", "")
            if not html:
                self.monitor["skipped"] += 1
                continue
            tables = re.findall(r'(<table\b[^>]*>.*?</table>)', html, re.DOTALL)
            if not tables:
                self.monitor["skipped"] += 1
                continue

            has_ids = any(re.search(r'>(\d+-\d+)<', t) for t in tables)
            if not has_ids:
                has_ids = any(re.search(r'>([A-Z]?\d+[\-\.]?\d*)<', t) for t in tables)
            if not has_ids and len(tables) == 1 and len(tables[0]) < 2000:
                self.monitor["skipped"] += 1
                continue

            tasks.append((sec, "\n".join(tables), i))

        if self.monitor["skipped"]:
            print(f"  Skipped {self.monitor['skipped']} non-table sections")

        total = len(tasks)
        all_results = []

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self._process_task, sec, html, idx, total): idx
                for sec, html, idx in tasks
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    items = future.result()
                    if items:
                        all_results.extend(items)
                except Exception as e:
                    self.monitor["llm_errors"] += 1
                    print(f"  [{idx+1}/{total}] ERROR: {e}")

        # Post-process: reattach orphans
        result = _post_process(all_results)
        self.monitor["orphans_reattached"] = result["stats"]["orphans_reattached"]

        fixed = result["fixed"]
        if result["stats"]["orphans_found"]:
            print(f"  Post-process: {result['stats']['orphans_found']} orphans, "
                  f"{result['stats']['orphans_reattached']} reattached, "
                  f"{result['stats']['orphans_dropped']} dropped")

        self._print_monitor(fixed)
        return fixed

    def _process_task(self, sec: dict, html: str, idx: int, total: int) -> list[dict]:
        h = sec.get("h2") or sec.get("h3") or "(no title)"
        tables = re.findall(r'(<table\b[^>]*>.*?</table>)', html, re.DOTALL)
        if not tables:
            return []

        # Merge continuation tables into logical groups
        groups = self._merge_table_groups(tables)

        all_items = []
        for gi, group_html in enumerate(groups):
            # Split oversized groups
            chunks = _split_large_html(group_html, self.MAX_CHARS_PER_CALL)
            if len(chunks) > 1:
                self.monitor["chunks_split"] += 1

            for ci, chunk in enumerate(chunks):
                label = h
                if len(groups) > 1 and len(chunks) > 1:
                    label = f"{h} [g{gi+1}/{len(groups)} c{ci+1}/{len(chunks)}]"
                elif len(groups) > 1:
                    label = f"{h} [g{gi+1}/{len(groups)}]"
                elif len(chunks) > 1:
                    label = f"{h} [c{ci+1}/{len(chunks)}]"

                items = self._call_llm(sec, chunk, idx, total, label, len(chunk))
                for item in items:
                    item["_source"] = {"chapter": sec.get("chapter", ""),
                                       "h2": sec.get("h2", ""), "h3": sec.get("h3", "")}
                all_items.extend(items)

        return all_items

    def _call_llm(self, sec: dict, html: str, idx: int, total: int,
                  label: str, size: int, retry_strict: bool = False) -> list[dict]:
        tokens = _estimate_tokens(html)
        system = SYSTEM_PROMPT
        if retry_strict:
            system += ("\n\n【重要提醒】上一次你输出的 JSON 缺少编号字段。"
                       "每个对象必须包含定额编号/清单编码/指标编号。"
                       "明细行（名称/单位/单价/数量）只能嵌套在父级对象中。")

        prompt = USER_PROMPT_TEMPLATE.format(
            chapter=sec.get("chapter", ""), h2=sec.get("h2", ""), h3=sec.get("h3", ""),
            work_content=sec.get("work_content", ""), unit=sec.get("unit", ""),
            html_table=html,
        )
        tag = " [RETRY strict]" if retry_strict else ""
        print(f"  [{idx+1}/{total}] {label[:40]}{tag} ({size:,} chars, ~{tokens:,} tokens)")

        response = self.client.chat(system, prompt)
        if response is None:
            self.monitor["empty_responses"] += 1
            return []

        items = _parse_json_response(response)
        if not items and response:
            self.monitor["parse_errors"] += 1
            print(f"  [{idx+1}/{total}] {label[:40]} [Parse Error] response={len(response)} chars, preview: {response[:100]}")

        n_id = sum(1 for x in items if any(k in x for k in _ID_FIELDS))
        n_detail = sum(1 for x in items if _DETAIL_KEYS & set(x.keys()))
        s_tag = f" ({n_id} with ID" + (f", {n_detail} orphan detail)" if n_detail else ")")
        print(f"  [{idx+1}/{total}] {label[:40]} → {len(items)} items{s_tag}")

        # Auto-retry: if HTML has clear 定额编号 but LLM returned 0 items with IDs
        if not retry_strict and n_id == 0 and html.count('定额编号') >= 1:
            print(f"  [{idx+1}/{total}] {label[:40]} [WARN] 0 IDs but HTML has 定额编号, retrying...")
            return self._call_llm(sec, html, idx, total, label, size, retry_strict=True)

        return items

    @staticmethod
    def _merge_table_groups(tables: list[str]) -> list[str]:
        """Merge continuation tables into parent tables by matching ID sequences."""
        if len(tables) <= 1:
            return tables
        groups, current, current_ids = [], [], None
        for tbl in tables:
            ids = re.findall(r'>(\d+-\d+)<', tbl)
            quota_header = '定额编号' in tbl
            if quota_header or not ids:
                if current: groups.append('\n'.join(current))
                current, current_ids = [tbl], set(ids) if ids else None
            elif ids and current_ids:
                new_ids = set(ids)
                if new_ids == current_ids or new_ids.issubset(current_ids):
                    current.append(tbl)
                else:
                    groups.append('\n'.join(current))
                    current, current_ids = [tbl], new_ids
            elif current:
                current.append(tbl)
        if current:
            groups.append('\n'.join(current))
        return groups

    def _print_monitor(self, items: list[dict]) -> None:
        """Print extraction health summary."""
        m = self.monitor
        n_id = sum(1 for x in items if any(k in x for k in _ID_FIELDS))
        n_orphan = sum(1 for x in items if not any(k in x for k in _ID_FIELDS))
        print(f"  Monitor: {m['total_sections']} sections, {m['skipped']} skipped, "
              f"{m['parse_errors']} parse errors, {m['empty_responses']} empty, "
              f"{m['llm_errors']} LLM errors, {m['chunks_split']} chunks split")
        print(f"  Output: {len(items)} items ({n_id} with ID, {n_orphan} other), "
              f"{m['orphans_reattached']} orphans reattached")


# ═══════════════════════════════════════════════════════════════
# Response parsing
# ═══════════════════════════════════════════════════════════════

def _parse_json_response(text: str | None) -> list[dict]:
    if not text:
        return []

    # Strategy 1: direct parse
    try:
        result = json.loads(text.strip())
        if isinstance(result, list): return result
        if isinstance(result, dict): return [result]
    except json.JSONDecodeError:
        pass

    # Strategy 2: ```json ... ``` block
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if m:
        try:
            result = json.loads(m.group(1).strip())
            if isinstance(result, list): return result
        except json.JSONDecodeError:
            pass

    # Strategy 3: outermost [ ... ]
    stripped = text.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        try: return json.loads(stripped)
        except json.JSONDecodeError: pass

    # Strategy 4: any [...]
    for m in re.finditer(r'\[[\s\S]*?\]', text):
        try:
            result = json.loads(m.group(0))
            if isinstance(result, list) and len(result) > 0: return result
        except json.JSONDecodeError: continue

    return []


# ═══════════════════════════════════════════════════════════════
# Pipeline entry
# ═══════════════════════════════════════════════════════════════

def extract_with_llm(sections: list[dict], client: LLMClient,
                     workers: int = 5, validate: bool = True) -> list[dict]:
    extractor = LLMExtractor(client, workers=workers)
    items = extractor.extract(sections)
    if validate and items:
        items = validate_all(items)
        print_validation_report(items)
    return items
