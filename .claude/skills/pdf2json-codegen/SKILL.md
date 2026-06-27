---
name: pdf2json-codegen
description: LLM 生成代码方式提取 PDF 表格数据。Agent 读取 Markdown 表结构，为每种表类型生成 Python 解析脚本，批量执行。1 次推理替代 N 次 API 调用，适合云端 token 敏感场景。
---

# PDF2json Codegen — Agent 代码生成提取

**这是纯 Agent Skill，无法在 Web UI 或 CLI 中执行。** 核心价值：用 Claude 的推理能力观察表结构 → 生成解析代码 → 代码批量处理所有同类表格。相比 `llm_direct`（每表调一次 LLM API），大幅降低 token 消耗。

## 触发条件

- 用户说"用代码提取" / "codegen" / "省钱模式"
- Web UI 执行完 `llm_direct` 后，用户想对比代码提取的效果
- `/pdf2json-codegen <run_id>` 或 `/pdf2json-codegen <markdown路径>`

---

## 路径约定

项目根 = 当前工作目录。所有操作相对于项目根。

---

## Phase 0: 定位输入

### 如果用户指定了 run_id

```bash
ls workspace/runs/<run_id>/markdown/
ls workspace/runs/<run_id>/extracted/
```

Markdown 在 `markdown/`，`llm_direct` 的提取结果在 `extracted/`（可用于对比）。

### 如果用户提供了 Markdown 文件路径

直接使用该文件。自动推断项目名，创建新的 run 目录。

---

## Phase 1: 识别表类型

**Agent 亲自阅读 Markdown**，识别所有 HTML `<table>` 的结构模式。

### 1a. 提取所有表格

```python
import re
md = open(md_path).read()
tables = re.findall(r'(<table\b[^>]*>.*?</table>)', md, re.DOTALL)
print(f"共 {len(tables)} 个表格")
```

### 1b. 对每类表提取特征向量

对每个 table：
- 是否有"定额编号"列？（`\d+-\d+` 模式）
- 是否有"清单编码"列？（长数字串）
- spec 列数？（6 列 DN300-800 / 5 列 / 其他）
- 是否有费用构成行（基价、人工费、材料费、机械费）？
- 明细行是"人工+材料+机械"三段式，还是扁平结构？
- 是否包含"工作内容"和"计量单位"的上下文？

### 1c. 聚类

Agent 根据以上特征将表格分组。通常一个项目只有 **1-3 种**表类型。

### 1d. 展示给用户确认

用 AskUserQuestion：
> "识别到 **{N} 种**表类型："
> "1. 标准定额表（定额编号 × 规格 → 费用构成 + 人工/材料/机械）— {count} 个表"
> "2. 全费用清单（清单编码 → 单价）— {count} 个表 （如果有）"
> "是否为每种类型生成解析代码？"

---

## Phase 2: 生成解析代码

Agent 为每种表类型**写一段独立的 Python 函数**。代码要求：

### 代码规范

```python
def parse_quota_table(html: str, context: dict) -> list[dict]:
    """
    解析标准定额表（定额编号 × 规格 → 费用构成 + 明细）。
    
    Args:
        html: HTML <table> 字符串
        context: {"h2": "...", "工作内容": "...", "计量单位": "...", ...}
    
    Returns:
        [{定额编号, 项目名称, 规格, 计量单位, 基价, 费用构成, 人工, 材料, 机械, ...}]
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    # ... 解析逻辑
    return results
```

### 必须遵守的规则

1. **使用 BeautifulSoup**解析 HTML（项目依赖中已有）
2. **处理 colspan/rowspan**：从 MinerU 的 HTML 输出中找到有效的列对应关系
3. **处理续表**：如果表格没有编号行，将其明细合并到上一表的结果中
4. **处理 parenthesized 数值**：`(0.200)` → `-0.200`（未计价材料）
5. **返回与 `llm_direct` 一致的 JSON 格式**：相同字段名，相同结构
6. **代码要独立可运行**：不依赖 LLM API，只依赖 bs4 + stdlib

---

## Phase 3: 执行并校验

### 3a. 批量执行

```python
# Agent 执行自己生成的代码
for table_html, context in tables_with_context:
    results = parse_quota_table(table_html, context)
    all_results.extend(results)
```

### 3b. 与 llm_direct 结果对比（如果存在）

```python
llm_items = json.load(open(f'workspace/runs/{run_id}/extracted/{file}.json'))
codegen_items = all_results

# 对比
llm_ids = set(item['定额编号'] for item in llm_items if '定额编号' in item)
codegen_ids = set(item['定额编号'] for item in codegen_items if '定额编号' in item)

print(f"llm_direct: {len(llm_items)} 条 ({len(llm_ids)} unique IDs)")
print(f"codegen:    {len(codegen_items)} 条 ({len(codegen_ids)} unique IDs)")
print(f"共有: {len(llm_ids & codegen_ids)}")
print(f"仅 llm_direct 有: {llm_ids - codegen_ids}")
print(f"仅 codegen 有:    {codegen_ids - llm_ids}")
```

### 3c. 字段级对比

对共同 ID，逐字段对比差异。报告给用户。

---

## Phase 4: 决策

### 情况 A: codegen 覆盖率 ≥ llm_direct → 使用 codegen 结果

告知用户：
> "✅ 代码提取 **{codegen_count}** 条，LLM 提取 **{llm_count}** 条。代码提取覆盖了更多数据。"

保存：
```bash
mkdir -p workspace/runs/<run_id>/codegen/
# 保存生成的代码
cp parse_*.py workspace/runs/<run_id>/codegen/
# 保存提取结果
# 写入 workspace/runs/<run_id>/codegen/extracted.json
```

更新 run.json：
```python
run_meta["config"]["backend"] = "llm_codegen"
run_meta["results"]["codegen_items"] = codegen_count
run_meta["results"]["codegen_vs_llm_coverage"] = len(codegen_ids & llm_ids) / len(llm_ids)
```

### 情况 B: codegen 覆盖率 < llm_direct → 分析原因

报告：
> "代码提取覆盖率 **{pct:.0%}**，低于 LLM 直接提取。差异可能原因："
> "1. 部分表格结构特殊，生成代码未覆盖"
> "2. 续表合并逻辑有遗漏"

让用户决定：A) 改进代码 B) 回退到 llm_direct 结果 C) 两者合并（codegen 为主，漏掉的用 llm_direct 补）

---

## Phase 5: 代码沉淀

无论结果如何，**将生成的代码保存到 run 目录**：

```bash
workspace/runs/<run_id>/codegen/
├── parse_quota_table.py     # 标准定额表解析函数
├── parse_cost_list.py       # 全费用清单解析函数（如有）
├── run_all.py               # 批量执行脚本
└── extracted.json           # 提取结果
```

下次遇到同类表格结构的 PDF 时，Agent 可以直接复用这些代码，无需重新生成。

---

## 与 llm_direct 的对比

| | llm_direct | llm_codegen |
|---|---|---|
| 谁执行 | pipeline 代码调 LLM API | **Claude Agent 亲自写代码** |
| LLM 调用次数 | N 次（每表一次） | **1 次**（生成代码） |
| Web UI 支持 | ✅ 可以 | ❌ 不能（需推理能力） |
| 确定性 | 低（API 返回有方差） | 高（代码逻辑确定） |
| 对 HTML 噪声容忍 | 高（语义理解） | 较低（代码机械执行） |
| 可复用 | 否 | 是（代码可沉淀为模板） |
| 适用场景 | 本地大模型（不在意 token） | 云端 API（token 敏感） |
