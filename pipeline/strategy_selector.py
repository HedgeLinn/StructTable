"""
Strategy selector — LLM-based table structure classification and dynamic prompt selection.

Flow (file-level, not table-level):
  1. Sample the 1~2 longest <table> from Markdown
  2. LLM classifies against pre-built templates
  3. If NO_MATCH → LLM generates a new strategy → saved for future use
  4. Selected strategy is used for ALL tables in this file
"""
import json
import re
from pathlib import Path

_TEMPLATES_PATH = Path(__file__).parent / "strategies" / "templates.json"


# ── Template I/O ──────────────────────────────────────────────


def load_templates() -> dict:
    """Load template library from templates.json."""
    if not _TEMPLATES_PATH.exists():
        return {"base_prompt": "", "templates": []}
    return json.loads(_TEMPLATES_PATH.read_text(encoding="utf-8"))


def save_templates(templates: dict) -> None:
    """Save template library to templates.json."""
    _TEMPLATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TEMPLATES_PATH.write_text(
        json.dumps(templates, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Table sampling ────────────────────────────────────────────


def sample_tables(sections: list[dict], n: int = 2, max_chars: int = 4000) -> list[str]:
    """Pick the 1~2 longest <table> snippets from sections for classification.

    Longer tables tend to have the most complete structure (headers, colspan,
    rowspan, detail rows). Snippets are truncated to max_chars to keep the
    classification LLM call cheap.
    """
    tables: list[tuple[int, str]] = []
    for sec in sections:
        html = sec.get("html_table", "")
        if not html:
            continue
        for m in re.finditer(r"(<table[^>]*>.*?</table>)", html, re.DOTALL):
            tables.append((len(m.group(1)), m.group(1)))

    # Longest first → most structurally complete
    tables.sort(key=lambda x: x[0], reverse=True)

    samples = []
    for _, t in tables[:n]:
        if len(t) <= max_chars:
            samples.append(t)
        else:
            samples.append(t[:max_chars] + "\n</table>")

    return samples


# ── LLM classification ──────────────────────────────────────


_CLASSIFY_PROMPT_TEMPLATE = """\
你是一个表格结构分析专家。根据以下表格样本的结构特征，选择最匹配的提取策略模板。

## 可用模板

{template_list}

## 要求
- 如果某个模板适合这张表的结构，直接输出该模板的 name（一个单词，如 flat、horizontal_split）
- 如果所有模板都不适合，输出 NO_MATCH
- 只输出名称或 NO_MATCH，不要任何解释

## 表格样本

{samples}"""


def select_or_generate_strategy(
    sections: list[dict],
    client,
    max_samples: int = 2,
) -> tuple[str, str]:
    """Select the best extraction strategy for this file.

    Args:
        sections: Parsed sections from document_parser
        client: LLMClient instance for classification calls

    Returns:
        (strategy_prompt, template_name)
    """
    templates_data = load_templates()
    base_prompt = templates_data["base_prompt"]
    template_list = templates_data["templates"]

    # Step 1: Sample representative tables
    samples = sample_tables(sections, n=max_samples)

    if not samples:
        # No tables at all — use base prompt only
        return base_prompt, "base_only"

    # Step 2: Build classification prompt
    tmpl_desc = "\n".join(
        f"- **{t['name']}**: {t['description']}" for t in template_list
    )
    sample_text = (
        samples[0]
        if len(samples) == 1
        else f"=== 样本 1 ===\n{samples[0]}\n\n=== 样本 2 ===\n{samples[1]}"
    )
    classify_prompt = _CLASSIFY_PROMPT_TEMPLATE.format(
        template_list=tmpl_desc, samples=sample_text,
    )

    # Step 3: LLM classification (lightweight call)
    response = client.chat(
        "你是表格结构分析专家。只输出模板名称或 NO_MATCH。",
        classify_prompt,
    )
    if response is None:
        # LLM failed — fallback to base prompt
        return base_prompt, "fallback"

    # Clean response: strip markdown formatting and quotes
    raw_line = response.strip().split("\n")[0].strip()
    match_name = re.sub(r'[*`~"\'"\']', "", raw_line).strip()

    # Step 4: Resolve match — exact first, then fuzzy
    resolved_name = None
    if match_name != "NO_MATCH":
        # Exact match
        for tmpl in template_list:
            if tmpl["name"] == match_name:
                resolved_name = tmpl["name"]
                break
        # Fuzzy match: prefix / contains / normalized equality
        if resolved_name is None:
            normalized = match_name.replace("-", "_").replace(".", "")
            for tmpl in template_list:
                tname = tmpl["name"].replace("-", "_").replace(".", "")
                if (normalized.startswith(tname)
                        or tname.startswith(normalized)
                        or normalized == tname):
                    resolved_name = tmpl["name"]
                    break

    if resolved_name:
        tmpl = next(t for t in template_list if t["name"] == resolved_name)
        strategy = base_prompt + "\n\n" + tmpl["prompt"]
        print(f"  [Strategy] Matched: {resolved_name}")
        return strategy, resolved_name

    # Step 5: Generate new strategy
    strategy = generate_new_strategy(samples, client, templates_data)
    print(f"  [Strategy] Generated new strategy")
    return strategy, "NEW"


# ── New strategy generation ─────────────────────────────────


_GENERATE_PROMPT_TEMPLATE = """\
分析以下 HTML 表格的结构，生成一套提取策略。

## 需要分析
1. 行列关系是怎样的？
2. 有没有合并单元格？合并方式（colspan/rowspan）？
3. 有没有横向展开（多列并列不同规格/区域）？
4. 有没有纵向嵌套（明细子区域：名称/单位/单价/数量）？
5. 编号/主键在哪里？
6. 数据的逻辑分组方式？

## 输出
基于分析，写一套提取策略（200 字以内），告诉 LLM 如何把这张表拆成 JSON：
- 每行/每列如何拆分为独立的 JSON 对象
- 哪些数据应该嵌套在子数组中
- 字段名怎么取

只输出策略文本，不要输出 JSON 示例。

## 表格样本

{sample}"""


def generate_new_strategy(
    samples: list[str],
    client,
    templates_data: dict,
) -> str:
    """Generate a new extraction strategy for an unmatched table structure.

    The new strategy is automatically saved to templates.json for future reuse.
    """
    sample = samples[0]
    prompt = _GENERATE_PROMPT_TEMPLATE.format(sample=sample)

    response = client.chat(
        "你是表格提取策略专家。分析表格结构并生成提取指令。",
        prompt,
    )
    if response is None:
        # LLM failed — fallback to base prompt
        return templates_data["base_prompt"]

    strategy_text = response.strip()

    # Save to templates
    new_name = f"auto_{len(templates_data['templates'])}"
    description = strategy_text[:80].replace("\n", " ")
    templates_data["templates"].append({
        "name": new_name,
        "description": description,
        "examples": [],
        "prompt": strategy_text,
        "auto_generated": True,
        "source_html_snippet": sample[:500],
    })
    save_templates(templates_data)
    print(f"  [Strategy] Saved as {new_name}: {description}")

    return templates_data["base_prompt"] + "\n\n" + strategy_text
