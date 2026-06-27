# StructTable

从 PDF 中提取表格数据，转换为结构化 JSON。使用 LLM 自动发现表格结构，无需预设字段名，支持任意表格格式。

## 项目背景

在日常工作中，大量有价值的数据被锁在 PDF 表格里——报告、清单、价目表、统计报表等。传统方法需要针对每种表格格式编写专门的解析脚本，维护成本高且无法应对格式变化。

StructTable 采用 **LLM 理解 + Agent 校验** 的双阶段架构，自动识别任意 PDF 表格的数据结构并提取为 JSON，无需预设字段名或编写解析规则。它既是一个可编程的 CLI 工具，也是一套与 Claude Code Agent 深度集成的智能工作流。

本项目仍在活跃开发中，欢迎提 Issue、PR，或直接 Fork 修改。如果你有想法，随时[提交 Issue](https://github.com/HedgeLinn/structural_PDF/issues) 或在 Discussions 中讨论。

## 快速开始

```bash
# 1. 安装
pip install -e .
pip install -e ".[ui]"       # Web UI

# 2. 配置
cp .env.example .env          # 编辑填入 LLM_API_KEY 和 MINERU_TOKEN

# 3. Web UI
streamlit run app/main.py --server.port 8501

# 4. 或 Claude Code Agent Skills
# /structtable-workspace upload <file.pdf>
# /structtable-run <file.pdf> --project <名称>
# /structtable-verify [run_id]
# /structtable-codegen <run_id>
```

## 架构

```
PDF → [MinerU/OCR_VL] → Markdown → [LLM/Agent提取] → 结构化 JSON
                                              │
                                      [Agent 校验补全]
```

## 功能

- **通用表格提取**: 自动识别编号列、规格展开、明细嵌套、合计关系，适应任意表格格式
- **双转换引擎**: MinerU（云端，推荐）/ OCR_VL（本地）
- **双提取方式**: LLM 逐表提取 / Agent 代码生成（省钱模式）
- **智能校验**: Agent 自动对比原始 Markdown 逐条修正数据
- **Web UI**: 可视化上传、配置、浏览、对比运行结果
- **工作区隔离**: 所有运行时数据与代码分离，互不污染

## 目录结构

```
structural_PDF/
├── pipeline/          # 核心 Python 代码（CLI + LLM 提取引擎）
├── app/               # Streamlit Web UI
├── .claude/skills/    # Claude Code Agent Skills
├── workspace/         # 运行时工作区（gitignore）
├── .env.example       # 配置模板
└── pyproject.toml     # 包定义
```

## 许可

内部项目 — 欢迎 Fork、修改、提 PR。
