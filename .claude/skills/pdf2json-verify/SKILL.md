---
name: pdf2json-verify
description: 检验 PDF2json 提取结果的完整性。自动对比原始 Markdown 修复遗漏数据。错误率 < 10% 自动补全，≥ 10% 生成报告。
---

# PDF2json Verify — 质量检验与 Agent 自动补全

对比原始 Markdown（可靠源）与提取的 JSON，逐条校验并自动修复。使用 Claude 自身的推理能力来理解表格语义。

## 触发条件

- `/pdf2json-run` 执行完毕后用户确认继续
- 用户说"检查提取质量" / "验证数据完整性" / "补全缺失数据"
- 用户指定 run_id：`/pdf2json-verify <run_id>`
- 未指定 → 自动选 `workspace/runs/` 下最近的有 `extracted/` 数据的 run

## 路径约定

项目根 = 当前工作目录（包含 `pipeline/` 和 `workspace/` 的目录）。所有路径相对于项目根。

---

## Phase 0: 定位 run

### 如果用户指定了 run_id

```bash
ls workspace/runs/<run_id>/extracted/
```

### 如果未指定

扫描 `workspace/runs/`，找到最新的 status=extracted 或 status=completed 的 run：

```bash
python -c "
import json, os
runs = sorted(
    [d for d in os.listdir('workspace/runs') if os.path.isdir(f'workspace/runs/{d}')],
    key=lambda d: os.path.getmtime(f'workspace/runs/{d}'), reverse=True
)
for r in runs:
    rj = f'workspace/runs/{r}/run.json'
    if os.path.exists(rj):
        meta = json.load(open(rj))
        if meta.get('status') in ('extracted', 'completed'):
            print(r)
            break
"
```

如果找不到任何 run，告知用户先运行 `/pdf2json-run`。

### 向用户确认

用 AskUserQuestion 确认：
> "将对以下运行进行质量检验：**<run_id>**（项目：<project>，条目：<N>）。确认继续？"

---

## Phase 1: 加载数据

读取两个核心文件：

```python
import json

# 1. 提取的 JSON
extracted_dir = f'workspace/runs/{run_id}/extracted'
json_files = [f for f in os.listdir(extracted_dir) if f.endswith('.json') and not f.startswith('temp')]
items = json.load(open(f'{extracted_dir}/{json_files[0]}'))

# 2. 原始 Markdown
markdown_dir = f'workspace/runs/{run_id}/markdown'
md_files = [f for f in os.listdir(markdown_dir) if f.endswith('.md')]
md_content = open(f'{markdown_dir}/{md_files[0]}').read()
```

向用户报告：
> "已加载：**{len(items)} 条**结构化数据 + **{len(md_content)} 字符**原始 Markdown"

---

## Phase 2: 六类问题检测

**作为 Agent，你需要亲自阅读 Markdown 和 JSON 进行交叉校验。** 不能只依赖 Python 脚本。以下是检测逻辑：

### 检测 1: 续表孤立

**Python 预筛**：
```python
from collections import Counter
ids = [item.get('定额编号') or item.get('清单编码') or item.get('清单编号') for item in items]
dup_ids = {id_ for id_, count in Counter(ids).items() if count > 1 and id_ is not None}
```

**Agent 确认**：对每组重复 ID，读取原始 Markdown 中两个条目所属的表格段落。判断：
- 主表条目：包含完整的基价 + 费用构成 + 明细
- 续表条目：可能基价=0 或明细为空

**修复**：将续表中的明细行合并到主表条目，删除续表的重复杂目。记录 `_fix_log`。

### 检测 2: 规格=ID 错误

**Python 预筛**：
```python
import re
id_pattern = re.compile(r'^\d+-\d+$')
spec_errors = [
    (i, item) for i, item in enumerate(items)
    if str(item.get('规格', '')) == str(item.get('定额编号', ''))
    and id_pattern.match(str(item.get('规格', '')))
]
```

**Agent 确认**：在 Markdown 中找到该条目的表格，读表头中的规格行（DN300/DN400...）。从相邻条目或表头推断正确规格值。

**修复**：将规格字段修正为正确的 DN 值。

### 检测 3: 费用合计不匹配

**Python 预筛**：
```python
fee_errors = []
for i, item in enumerate(items):
    fee = item.get('费用构成')
    base = item.get('基价')
    if fee and base is not None:
        s = fee.get('人工费', 0) + fee.get('材料费', 0) + fee.get('机械费', 0)
        if abs(base - s) > 1.0:
            fee_errors.append((i, item, base, s))
```

**Agent 确认**：在 Markdown 表格中定位该条目，核对"基价"列和"人工费/材料费/机械费"三列的原始数值。OCR 列偏移通常导致整个列的值错位，Agent 需找出正确的对应关系。

**修复**：从 Markdown 提取正确数值覆盖 JSON。

### 检测 4: 重复条目

**Python 预筛**：
```python
import hashlib
seen, dups = {}, []
for i, item in enumerate(items):
    clean = {k: v for k, v in item.items() if not k.startswith('_')}
    h = hashlib.md5(json.dumps(clean, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if h in seen:
        dups.append((i, seen[h]))
    else:
        seen[h] = i
```

**修复**：保留第一个，删除重复。记录 `_fix_log`。

### 检测 5: 计量单位格式错误

**Python 预筛**：
```python
unit_errors = [
    (i, item) for i, item in enumerate(items)
    if not item.get('计量单位', '') or item.get('计量单位', '').strip() == ''
    or '|' in str(item.get('计量单位', ''))
]
```

**Agent 确认**：在 Markdown 中搜索该条目所在章节的"计量单位："声明，或从同 h2 下其他条目获取。

**修复**：填入正确的计量单位。

### 检测 6: 章节归属异常

**Agent 确认**：通读 Markdown 中的所有 `##` 和 `###` 标题，列出章节列表。与 JSON 中 `_source.h2` 的值比对。如果某个章节在 Markdown 中有表格但 JSON 中无对应条目，说明该章节数据被漏提或错归。

**修复**：如果数据存在但 h2 错误 → 修正 `_source.h2`。如果完全漏提 → Agent 从 Markdown 手动提取该章节的表格数据。

---

## Phase 3: 错误率计算

```python
affected = len(fixed_indices)  # 去重后的受影响条目数
error_rate = affected / len(items) if items else 0
```

向用户报告：
> "检验结果：**{affected}/{len(items)} = {error_rate:.1%}** 条目受影响"

---

## Phase 4: 决策分叉

### 情况 A: error_rate ≤ 10% → 自动补全

告知用户：
> "错误率 {error_rate:.1%} 在 10% 以内，我现在自动补全。"
> "将逐条修复 {affected} 个条目，每条标注修复依据和置信度。"

逐条修复，每修复一条追加 `_fix_log`：

```json
{
  "_fix_log": [{
    "action": "merge_continuation",
    "original_value": "基价=0, 材料=[], 机械=[]",
    "corrected_value": "基价=5245.0, 材料=[10项], 机械=[5项]",
    "evidence": "原始 Markdown 中 9-10 续表表格（第XX行），ID 集合与主表一致",
    "confidence": "high"
  }]
}
```

**confidence 等级**：
- `high` — 直接从 Markdown 精确匹配到正确值
- `medium` — 从上下文推断（如同 h2 下其他条目）
- `low` — 无法确定，**保留原值，标记 `_unresolved`**

保存修复结果：
```bash
mkdir -p workspace/runs/<run_id>/verified/
# 写入 _fixed.json
```

更新 run.json：
```python
run_meta["results"]["verified"] = True
run_meta["results"]["fixed_count"] = len(fixed)
run_meta["results"]["unresolved_count"] = len(unresolved)
run_meta["results"]["error_rate"] = error_rate
run_meta["timing"]["verification_done"] = datetime.now().isoformat()
run_meta["status"] = "completed"
```

最终报告：
```
✅ 自动补全完成

   📊 修复条目: {fixed} 条
   ⚠️ 未解决: {unresolved} 条（confidence=low，已标记 _unresolved）
   📂 输出: workspace/runs/{run_id}/verified/{file}_fixed.json
   📋 修复日志: 每条含 _fix_log，可追溯每次修改
```

### 情况 B: error_rate > 10% → 生成报告

**不执行自动修复。** 告知用户：
> "⚠️ 错误率 {error_rate:.1%} 超过 10% 阈值，建议人工介入。我为你生成详细报告。"

生成 Markdown 报告到 `workspace/runs/<run_id>/reports/quality_report.md`：

包含：
- 概要（文件、条目数、错误率、阈值、判定）
- 问题分布表（类别、数量、占比）
- 每类问题的详细清单（定额编号、描述、建议修正值）
- 建议（检查转换器、检查 LLM API、手工检查特定条目）

```
⚠️ 错误率 {error_rate:.1%} 超过 10% 阈值。

📄 详细报告: workspace/runs/{run_id}/reports/quality_report.md

💡 建议:
   1. 查看报告中的问题清单
   2. 考虑切换转换器（MinerU ↔ OCR_VL）
   3. 或检查原始 PDF 的扫描质量
   4. 修复后可重新运行 /pdf2json-verify {run_id}
```

---

## Phase 5: 询问是否导出

用 AskUserQuestion 询问：
> "质量检验完成。是否需要我帮你在 Claude Code 中直接运行 /pdf2json-run 处理更多文件？"

选项：
- "继续处理其他 PDF"
- "查看所有运行记录"
- "结束"
