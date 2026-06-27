---
name: pdf2json-verify
description: 检验 PDF2json 提取结果的完整性，自动对比原始 Markdown 修复遗漏数据。可指定 run_id 或自动选择最近的 run。当用户提到"检查提取质量"、"验证数据完整性"、"补全缺失数据"或在 pdf2json-run 完成后触发。
---

# PDF2json Verify — 质量检验与 Agent 自动补全

对比原始 Markdown 与提取的 JSON，逐条校验并自动修复。产物写入 `workspace/runs/<run_id>/verified/`。

## 触发条件

- `/pdf2json-run` 执行完毕后自动建议
- 用户说"检查提取结果" / "验证质量" / "补全数据"
- 用户指定 run_id：`/pdf2json-verify <run_id>`
- 未指定 run_id → 自动选择 `workspace/runs/` 中最近的 `status=extracted` 的 run

---

## 执行流程

```
Step 0: 定位 run  → 确定 run_id + 读取 run.json
Step 1: 加载数据   → extracted JSON + 原始 Markdown
Step 2: 6 类检测   → 逐条扫描，分类计数
Step 3: 错误率计算 → 受影响条目 / 总条目
Step 4: 决策分叉   → ≤10% 自动补全 / >10% 生成报告
Step 5: 更新 run.json + 输出摘要
```

---

## Step 0: 定位 run

### 如果用户指定了 run_id

```bash
ls workspace/runs/<run_id>/extracted/
```

### 如果未指定

扫描 `workspace/runs/`，找到最新的 `status=extracted` 或 `status=running` 的 run：

```python
runs = sorted(Path("workspace/runs").iterdir(), key=os.path.getmtime, reverse=True)
for run in runs:
    with open(run / "run.json") as f:
        meta = json.load(f)
    if meta["status"] in ("extracted", "completed"):
        run_id = run.name
        break
```

---

## Step 1: 加载数据

```python
extracted_json = run_dir / "extracted" / "*.json"
md_path = run_dir / "markdown" / "*.md"
chunks_json = run_dir / "extracted" / "*_chunks.json"  # OCR_VL only

items = json.load(open(extracted_json))
md_content = open(md_path).read()
```

---

## Step 2: 六类问题检测

### 检测 1: 续表孤立（Duplicate ID → 基价=0 或明细为空）

Agent 读取原始 Markdown，对每组重复 ID，确认哪个是主表、哪个是续表。合并补充缺失字段。

### 检测 2: 规格=ID 错误（规格匹配 `\d+-\d+` 模式）

Agent 从 Markdown 表格表头读取正确的规格值（DN 序列），修正错误条目。

### 检测 3: 费用合计不匹配（`abs(基价 - sum(费用构成)) > 1.0`）

Agent 在 Markdown 中定位该条目，读取原始数值，替换 JSON 中的错误字段。

### 检测 4: 重复条目（完全相同）

代码去重：保留第一个，删除重复。标记 `_fix_log`。

### 检测 5: 计量单位格式错误（空值或含 `|` 字符）

Agent 从同一 h2 下其他条目或 Markdown 章节头提取正确的计量单位。

### 检测 6: 章节归属异常（chunks 中有但 JSON 中无的章节）

检查 Markdown 中所有章节的表是否在 JSON 中有对应的条目。缺失的从 Markdown 手动提取。

---

## Step 3: 错误率计算

```python
affected = set()  # 受影响条目的 index
for category, indices in detection_results.items():
    affected.update(indices)

error_rate = len(affected) / len(items)
```

---

## Step 4: 决策分叉

### 情况 A: error_rate ≤ 10% → Agent 自动补全

逐条修复。每条修复记录 `_fix_log`：

```json
{
  "_fix_log": [
    {
      "action": "merge_continuation",
      "original_value": "基价=0, 明细为空",
      "corrected_value": "基价=5245.0, 材料=[...]",
      "evidence": "Markdown 第XX行，续表与主表 ID 集合相同",
      "confidence": "high"
    }
  ]
}
```

confidence 等级：
- `high` — 直接从 Markdown 精确匹配
- `medium` — 从上下文推断
- `low` — 无法确定，保留原值

**不修 low confidence 的条目**，标记为 `_unresolved`。

保存到：`workspace/runs/<run_id>/verified/<file>_fixed.json`

### 情况 B: error_rate > 10% → 生成报告

保存报告到：`workspace/runs/<run_id>/reports/quality_report.md`

包含问题分布表、每类问题的详细清单、建议。

---

## Step 5: 更新 run.json

```python
run_meta["results"]["verified"] = True
run_meta["results"]["fixed_count"] = fixed_count
run_meta["results"]["unresolved_count"] = unresolved_count
run_meta["results"]["error_rate"] = error_rate
run_meta["timing"]["verification_done"] = datetime.now().isoformat()

if error_rate <= 0.10:
    run_meta["status"] = "completed"
else:
    run_meta["status"] = "needs_review"
```

---

## 输出摘要模板

```
📊 PDF2json 质量检验报告

📁 Run: 20260627_1430_退役管道第一册_mineru_llmdirect
📊 总条目: 144

🔍 问题检测:
  检测1 续表孤立:       12 条
  检测2 规格=ID错误:      0 条
  检测3 费用不匹配:       3 条
  检测4 重复条目:         4 条
  检测5 计量单位错误:     6 条
  检测6 章节归属异常:     0 条
  ─────────────────────────
  受影响条目 (去重):     19 / 144 = 13.2%

⚠️ 错误率 13.2% 超过 10% 阈值。
📄 详细报告: workspace/runs/<run_id>/reports/quality_report.md
```

或（如果 ≤10%）：

```
✅ 自动补全完成
  修复条目: 12
  未解决: 1
  输出: workspace/runs/<run_id>/verified/<file>_fixed.json
```

## 关键文件路径

| 文件 | 路径 |
|------|------|
| 提取 JSON | `workspace/runs/<run_id>/extracted/` |
| 原始 Markdown | `workspace/runs/<run_id>/markdown/` |
| 修复后 JSON | `workspace/runs/<run_id>/verified/` |
| 质量报告 | `workspace/runs/<run_id>/reports/` |
| run 元数据 | `workspace/runs/<run_id>/run.json` |
