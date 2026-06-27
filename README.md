# StructTable

从 PDF 中提取表格数据，转换为结构化 JSON。使用 LLM 自动发现表格结构，无需预设字段名，支持多种表格格式。

## 快速开始

```bash
# 1. 安装
pip install -e .
pip install -e ".[ui]"       # Web UI

# 2. 配置
cp .env.example .env          # 编辑填入 LLM_API_KEY 和 MINERU_TOKEN

# 3. 运行
streamlit run app/main.py --server.port 8501

# 或使用 Claude Code Agent Skills
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

- **PDF 表格提取**: 自动识别表格结构，转换为 JSON
- **双转换引擎**: MinerU（云端推荐）/ OCR_VL（本地）
- **双提取方式**: LLM 逐表提取 / Agent 代码生成
- **智能校验**: Agent 自动对比原始数据修复遗漏
- **Web UI**: 可视化上传、配置、浏览、对比
- **工作区隔离**: 运行时数据与代码分离

## 许可

内部项目
