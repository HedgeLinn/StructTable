# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🚀 新用户入口

当首次在此项目中响应新用户时，按以下顺序引导：

1. **简介**："这是 **StructTable**——从 PDF 中提取表格数据并转换为结构化 JSON 的工具。支持两种 PDF 转换引擎（MinerU 云端 / OCR_VL 本地）和两种提取方式（LLM 逐表提取 / Agent 代码生成）。"

2. **检测状态**：
```bash
test -f .env && echo "✅ .env 已配置" || echo "⚠️ .env 未配置 — 需要设置 LLM API"
test -d workspace && echo "✅ workspace/ 已就绪" || echo "⚠️ workspace/ 待初始化"
python -c "import bs4, requests, dotenv; print('✅ 核心依赖已安装')" 2>&1 || echo "⚠️ 依赖缺失 — pip install -e ."
```

3. **引导缺失步骤**（参考 `.claude/skills/structtable-run/SKILL.md` Phase 0）

4. **推荐技能**：
   - 提取 PDF 表格 → `/structtable-workspace upload` → `/structtable-run`
   - 检查数据质量 → `/structtable-verify`
   - 省 API 调用 → `/structtable-codegen`
   - 管理工作区 → `/structtable-workspace list` / `clean`

5. **三条核心规则**：
   - 所有路径相对于项目根目录（含 `pipeline/` 的目录），不使用绝对路径
   - 重要操作前必须和用户确认（删除运行、选择转换引擎、覆盖已有结果）
   - 每个阶段完成后，主动建议下一步（上传→运行→验证→导出）

---

## 项目概述

从 PDF 中提取表格数据，转换为结构化 JSON。支持多种表格格式，自动发现表格结构，无需预设字段名。

## 架构

```
PDF → [转换引擎: mineru|ocr_vl] → Markdown
     → [document_parser.py] → sections (HTML tables + 上下文)
     → [提取方式: llm_direct|llm_codegen] → 结构化 JSON
     → [validate_all()] → 质量门控 (错误率 < 10% → Agent 自动补全)
     → 最终 JSON (含 _fix_log)
```

### 两条 PDF 转换路径

| | MinerU | OCR_VL |
|---|---|---|
| 输出质量 | 干净 HTML 表格，明细行天然分离 | HTML 表格，合并单元格可能有误 |
| 后处理 | 无需 | 需 `postprocess.py` (ODL 融合修复) |
| 依赖 | 仅 API token | PyMuPDF + OCR_VL 服务 |
| 适用 | **推荐首选** | MinerU 不可用时 |

### 两条提取方式

| | `llm_direct` | `llm_codegen` |
|---|---|---|
| **执行者** | pipeline 代码调 LLM API | **Agent 亲自读表→写代码→执行** |
| **Web UI** | ✅ | ❌ Agent Only |
| **Agent Skill** | `/structtable-run` | `/structtable-codegen` |
| **LLM 调用** | N 次（每表一次） | 1 次（生成代码） |
| **适用** | 本地大模型 (不在意 token) | 云端 API (token 敏感) |

> **关键**：`llm_codegen` 不是 pipeline 代码功能，是纯 Agent Skill。

## CLI 命令参考

```bash
# 安装
pip install -e .
pip install -e ".[ocr]"      # OCR_VL 需要 PyMuPDF
pip install -e ".[ui]"       # Web UI（Streamlit）
pip install -e ".[dev]"      # 开发依赖（lxml）

# 配置
cp .env.example .env          # 填入 LLM_API_KEY 和 MINERU_TOKEN

# === CLI 管线 ===
# 单文件转换（PDF 或 Markdown → JSON）
python -m pipeline.main convert input.pdf --output result.json
python -m pipeline.main convert input.md --output result.json --dry-run
python -m pipeline.main convert input.pdf -c mineru  # 指定转换器

# 批量处理目录
python -m pipeline.main batch input_dir/ --output output_dir/ -c mineru

# 校验已有 JSON
python -m pipeline.main validate result.json --output annotated.json

# === Web UI ===
streamlit run app/main.py --server.port 8501

# === Agent Skills ===
# /structtable-workspace upload|list|compare|clean
# /structtable-run [file] --project <name>
# /structtable-codegen <run_id>
# /structtable-verify [run_id]
```

### CLI 参数

| 命令 | 参数 | 说明 |
|------|------|------|
| `convert` | `input` | PDF 或 Markdown 文件路径 |
| `convert` | `--output / -o` | 输出 JSON 路径（默认 `output5/<stem>.json`） |
| `convert` | `--converter / -c` | `ocr_vl` 或 `mineru`（默认读 `CONVERTER` 环境变量） |
| `convert` | `--skip-fusion` | 跳过 ODL 融合后处理（仅 OCR_VL 路径） |
| `convert` | `--dry-run` | 仅解析 section 不执行 LLM 提取 |
| `batch` | `input` | 含 `.md` 或 `.pdf` 文件的目录 |
| `batch` | `--output / -o` | 输出目录 |
| `batch` | `--converter / -c` | PDF 转换器（仅 PDF 输入生效） |
| `validate` | `input` | JSON 文件路径 |
| `validate` | `--output / -o` | 标注后的输出路径 |

## 代码结构与数据流

```
pipeline/
├── main.py                # CLI 入口：convert / batch / validate 三个子命令
├── config.py              # 环境变量配置（LLM_CONFIG, OCR_CONFIG, MINERU_CONFIG）
├── document_parser.py     # parse_sections() → sections 列表
├── llm_extractor.py       # LLMClient + extract_with_llm() + SYSTEM_PROMPT
├── postprocess.py         # OCR_VL 专用：HTML 修复（ODL 融合）
├── utils.py               # parse_number(), write_json(), validate_all()
└── pdf2markdown/
    ├── base.py            # ConverterAdapter ABC
    ├── mineru.py          # MinerU 云端适配器（异步轮询）
    └── ocr_vl.py          # OCR_VL HTTP API 适配器

app/                       # Streamlit Web UI
├── main.py                # 入口 + 侧边栏
├── utils.py               # 工作区扫描、run 读写
└── pages/                 # dashboard / upload_run / results / history / compare

workspace/                 # 运行时数据（.gitignore）
├── uploads/<项目名>/*.pdf
└── runs/<YYYYMMDD_HHMM_*>/  # run.json + markdown/ + extracted/ + verified/ + codegen/ + reports/ + logs/
```

### 核心数据流

1. **`document_parser.parse_sections(md_content)`** → `list[dict]`，每个 section 包含 `chapter, h2, h3, work_content, unit, html_table`。通过正则切分章节，自动合并跨页重复 section
2. **`llm_extractor.extract_with_llm(sections, client, workers)`** → 线程池并发调 LLM API，每 section 一次调用。内置续表合并、大表拆分、孤立明细归附
3. **`utils.validate_all(data)`** → 给每条数据附加 `_validation` 字段，计算准确率/完整率
4. **`utils.parse_number(val)`** → 数值解析核心函数，处理中文全角括号 `（0.200）→ -0.200`

### LLM 提取核心机制

- **无预设 schema**：System prompt 描述通用规则，LLM 自行从 HTML 发现字段名（见 `llm_extractor.py` 的 `SYSTEM_PROMPT`）
- **并发**：`LLM_WORKERS`（默认 5）线程并行
- **JSON 解析容错**：四级回退 — 直接解析 → code block 提取 → 最外层括号 → 任意括号组
- **零 ID 重试**：输出不含编号但 HTML 含编号列时，自动重试
- **API**：OpenAI 兼容 `/chat/completions` 端点

## 已知数据问题（Agent 自动补全处理的 6 类）

| # | 问题 | 根因 | 检测 | Agent 可修? |
|---|------|------|------|:---:|
| 1 | **续表孤立** | 分页截断 | 相同 ID 出现多次 + 一个数据为空 | ✅ |
| 2 | **规格=ID 错误** | 续表缺规格行 | 规格值匹配编号模式 | ✅ |
| 3 | **数值合计不匹配** | 列偏移 | `abs(主值 - sum(子项)) > 1.0` | ✅ |
| 4 | **重复条目** | chunk 拆分重叠 | 相同 ID + 相同 hash | ❌ 代码去重 |
| 5 | **单位格式错误** | 噪声字符 | 空值或含 `\|` | ✅ |
| 6 | **章节归属错误** | 解析器匹配错误 | 章节与内容不匹配 | ⚠️ 部分 |

核心原则：**对比原始 Markdown（可靠源）与提取的 JSON，逐条校验修正**。

## Web UI + Agent 协作

```
Web UI (Streamlit)                 Claude Code Agent
   ├─ 上传 PDF / 选引擎              │
   ├─ 执行 llm_direct → workspace/   │
   ├─ 展示结果                       │
   │   /structtable-verify ────────▶ 读 Markdown + JSON → 校验补全
   │   /structtable-codegen ───────▶ 读表→写代码→执行
   │  ◀───────────────────── 回写 verified/ 或 codegen/
   ├─ 刷新查看 Agent 结果             │
   └─ 导出                           │
```

- **共享数据总线**：`workspace/`
- **Web UI** 负责：上传、选引擎、跑 `llm_direct`、可视化、对比
- **Agent** 负责：`llm_codegen`（写代码提取）、`verify`（智能校验补全）

## Agent Skills

| Skill | 触发 | 职责 | 执行者 |
|-------|------|------|--------|
| `structtable-workspace` | `/structtable-workspace <upload\|list\|compare\|clean>` | 管理工作区 | Agent |
| `structtable-run` | `/structtable-run [文件] --project <名>` | 交互引导 + 执行管线 | Agent 调 CLI |
| `structtable-codegen` | `/structtable-codegen <run_id>` | 读表→写代码→执行→校验 | **纯 Agent** |
| `structtable-verify` | `/structtable-verify [run_id]` | 6 类检测 + ≤10% 自动补全 | **纯 Agent** |

## 环境变量配置

| 分组 | 关键变量 | 用途 |
|------|---------|------|
| LLM | `LLM_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_WORKERS` | 提取模型 |
| CONVERTER | `CONVERTER` | `ocr_vl` / `mineru` |
| OCR | `OCR_URL`, `OCR_DPI` | OCR_VL 路径 |
| MinerU | `MINERU_TOKEN`, `MINERU_MODEL_VERSION` | MinerU 路径 |

完整变量列表见 `.env.example`。

## 测试与 Lint

当前项目未配置自动化测试框架和 lint 工具。修改代码后通过以下方式验证：

1. **dry-run 验证解析**：`python -m pipeline.main convert input.md --dry-run` — 检查 section 切分是否正确
2. **单文件提取验证**：`python -m pipeline.main convert input.md -o test.json` — 检查 LLM 提取结果
3. **校验输出**：`python -m pipeline.main validate test.json` — 运行 validate_all() 质量报告
