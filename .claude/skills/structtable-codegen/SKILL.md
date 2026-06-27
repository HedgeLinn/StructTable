---
name: structtable-codegen
description: Agent 代码生成方式提取 PDF 表格数据。读取 Markdown 表结构，为每种表类型生成 Python 解析脚本，批量执行。1 次推理替代 N 次 API 调用。
---

# StructTable Codegen — Agent 代码生成提取

纯 Agent Skill。Agent 读取 Markdown 中的 HTML 表格，识别表结构模式，生成 Python 解析代码，批量执行。

## 触发条件
- 用户说"用代码提取" / "codegen" / "省钱模式"
- /structtable-codegen <run_id> 或 /structtable-codegen <markdown路径>

## Phase 1: 识别表类型
Agent 阅读 Markdown，提取所有 HTML <table>，按结构特征聚类。
用 AskUserQuestion 展示类型让用户确认。

## Phase 2: 生成解析代码
Agent 为每种类型写 parse_*.py 函数:
- 使用 BeautifulSoup 解析 HTML
- 处理 colspan/rowspan
- 处理续表合并
- 不含 LLM API 依赖

## Phase 3: 执行并校验
批量执行代码。与 llm_direct 结果对比（如果存在）。

## Phase 4: 决策
- 代码覆盖更好 → 使用代码结果 → 保存到 codegen/
- 覆盖不足 → 分析原因，让用户选择改进或回退

## Phase 5: 代码沉淀
保存到 workspace/runs/<run_id>/codegen/ 供复用。

## 与 llm_direct 对比
| | llm_direct | llm_codegen |
|---|---|---|
| 谁执行 | pipeline 调 LLM API | Agent 写代码 |
| LLM 调用次数 | N 次 | 1 次 |
| Web UI 支持 | ✅ | ❌ |
| 确定性 | 低 | 高 |
| 可复用 | 否 | 是 |
