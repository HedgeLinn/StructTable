# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🚀 新用户入口（Claude 打开项目后，首先执行此流程）

当你（Claude Code Agent）首次在此项目中响应新用户时，请按以下顺序引导：

### 1. 欢迎与概述
向用户简要介绍："这是 **StructTable**——从 PDF 中提取表格数据并转换为结构化 JSON 的工具。支持两种 PDF 转换引擎（MinerU 云端 / OCR_VL 本地）和两种提取方式（LLM 逐表提取 / Agent 代码生成）。"

### 2. 检测项目状态
```bash
echo "=== StructTable 状态检测 ==="
test -f .env && echo "✅ .env 已配置" || echo "⚠️ .env 未配置 — 需要设置 LLM API"
test -d workspace && echo "✅ workspace/ 已就绪" || echo "⚠️ workspace/ 待初始化"
python -c "import bs4, requests, dotenv; print('✅ 核心依赖已安装')" 2>&1 || echo "⚠️ 依赖缺失 — pip install -e ."
```

### 3. 交互式引导
根据检测结果，用 AskUserQuestion 引导用户完成缺失步骤。参考 `.claude/skills/structtable-run/SKILL.md` 中的 Phase 0 流程。

### 4. 技能推荐
根据用户意图推荐合适的 Skill：
- 用户想提取 PDF 表格 → 建议 `/structtable-workspace upload` → `/structtable-run`
- 用户想检查数据质量 → 建议 `/structtable-verify`
- 用户想省钱（少调 API）→ 建议 `/structtable-codegen`
- 用户想管理工作区 → 建议 `/structtable-workspace list` / `clean`

### 5. 三条核心规则
1. **所有路径相对于项目根目录**（包含 `pipeline/` 的目录），不要使用绝对路径
2. **重要操作前必须和用户确认**（删除运行、选择转换引擎、覆盖已有结果）
3. **每个阶段完成后，主动建议下一步**（上传→运行→验证→导出）

---

## 项目概述

从 PDF 中提取表格数据，转换为结构化 JSON。支持多种表格格式，自动发现表格结构，无需预设字段名。

## 完整架构

```
                          PDF
                           │
              ┌────────────┴────────────┐
              │   转换引擎选择            │
              ├─────────────────────────┤
              │ mineru (推荐) │ ocr_vl   │
              │ 云端异步 API  │ VLM逐页  │
              │ 干净HTML表格   │ HTML表格  │
              └────────────┬─┬──────────┘
                           │ │
                         Markdown
                           │
                  [document_parser.py]
                    章节切分 + HTML table 提取
                           │
                        HTML tables + 上下文 (sections)
                           │
              ┌────────────┴────────────┐
              │   提取方式选择            │
              ├───────────┬─────────────┤
              │ llm_direct│ llm_codegen │
              │ (Web UI✅)│ (Agent Only)│
              │ CLI 调LLM │ Agent读表    │
              │ N次LLM调用│ →写代码→执行 │
              └───────────┴─┬───────────┘
                          │
                    结构化 JSON
                          │
              ┌───────────┴───────────┐
              │   QUALITY GATE        │
              │   validate_all()      │
              │   准确率 & 完整率计算  │
              └───────────┬───────────┘
                          │
                   错误率 < 10%？
                   /        \
                 YES         NO
                  │           │
          ┌───────┴──┐   ┌──┴──────────┐
          │ Agent    │   │ 修正代码     │
          │ 自动补全 │   │ 或人工介入   │
          └───────┬──┘   └──────┬───────┘
                  │              │
                  └──────┬───────┘
                         │
                   最终 JSON (含 _fix_log)
```

## 两条 PDF 转换路径

| | MinerU | OCR_VL |
|---|---|---|
| 输出质量 | 干净 HTML 表格，明细行天然分离 | HTML 表格，合并单元格可能有误 |
| 后处理 | 无需 | 需 postprocess.py (ODL 融合修复) |
| 依赖 | 仅 API token | PyMuPDF + OCR_VL 服务 |
| 适用 | **推荐首选** | MinerU 不可用时 |

## 两条提取方式

| | `llm_direct` | `llm_codegen` |
|---|---|---|
| **谁执行** | pipeline 代码调 LLM API | **Agent 亲自读表→写代码→执行** |
| **Web UI 支持** | ✅ | ❌ Web UI 无法替代 Agent 推理 |
| **Agent Skill** | `/structtable-run` | `/structtable-codegen` |
| **LLM 调用次数** | N 次（每表一次） | **1 次**（生成代码） |
| **确定性** | 低（API 返回有方差） | 高（代码逻辑确定） |
| **适用** | 本地大模型 (不在意 token) | 云端 API (token 敏感) |

> **关键区分**：`llm_codegen` 不是 pipeline 代码功能，是 Agent Skill。

## 已知数据问题（Agent 自动补全需处理的 6 类问题）

| # | 问题类别 | 根因 | 检测方法 | Agent 可修? |
|---|---------|------|---------|:---:|
| 1 | **续表孤立** — 跨页表格被提取为两个独立条目 | 分页截断 | 相同 ID 出现多次 + 其中一个数据为空 | ✅ |
| 2 | **规格=ID 错误** — 规格字段被填入编号值 | 续表缺规格行，LLM 猜测错误 | 规格值匹配编号模式 | ✅ |
| 3 | **数值合计不匹配** — 主值 ≠ 子项之和 | 列偏移 | `abs(主值 - sum(子项)) > 1.0` | ✅ |
| 4 | **重复条目** — 同一 ID 出现两次完全相同 | 大表 chunk 拆分重叠 | 相同 ID + 相同内容 hash | ❌ 代码去重 |
| 5 | **单位格式错误** — 值为 `\| \| \|` 或空 | 读入噪声字符 | 空值或含 `\|` 字符 | ✅ |
| 6 | **章节归属错误** — 表格被归入错误的章节 | 解析器匹配错误 | 章节与实际内容不匹配 | ⚠️ 部分 |

Agent 自动补全的核心原则：**对比原始 Markdown（可靠源）与提取的 JSON，逐条校验修正**。

## 工作区架构（运行时隔离）

所有运行时数据存入 `workspace/`，与代码完全分离。`workspace/` 在 `.gitignore` 中。

```
workspace/
├── uploads/                              # 用户上传的原始 PDF
│   └── <项目名>/
│       └── *.pdf
│
└── runs/                                 # 每次运行的完整产物
    └── <YYYYMMDD_HHMM_<项目>_<converter>_<backend>/
        ├── run.json                      # 运行元数据
        ├── markdown/                     # PDF 转换结果
        ├── extracted/                    # LLM 提取的原始 JSON
        ├── verified/                     # Agent 验证+补全后的 JSON
        ├── codegen/                      # Agent 代码生成结果
        ├── reports/                      # 质量报告
        └── logs/                         # 运行日志
```

## 项目结构

```
structural_PDF/
├── pipeline/                  # Python 核心代码
│   ├── main.py                # CLI 入口 (convert / batch / validate)
│   ├── config.py              # 环境变量配置
│   ├── document_parser.py     # Markdown 章节切分 + HTML table 提取
│   ├── llm_extractor.py       # llm_direct 后端：LLM 逐表提取引擎
│   │                          #   - 续表识别合并、大表拆分、孤立条目归附
│   │                          #   - 异常输出自动重试 + 健康监控
│   ├── postprocess.py         # OCR_VL 路径专用：HTML 修复
│   ├── utils.py               # 数值解析、JSON 格式化、校验
│   └── pdf2markdown/          # PDF→Markdown 转换适配器
│       ├── base.py            #   ConverterAdapter ABC
│       ├── mineru.py          #   MinerU 云端适配器
│       ├── ocr_vl.py          #   OCR_VL HTTP API 适配器
│       └── batch_convert.py   #   批量转换脚本
├── workspace/                 # 运行时工作区（gitignore）
│   ├── uploads/               #   用户上传的 PDF
│   └── runs/                  #   每次管线的完整产物
├── app/                       # Web UI（Streamlit 前端）
│   ├── main.py                #   入口 + 侧边栏导航
│   ├── utils.py               #   工作区扫描、run 读写
│   └── pages/                 #   功能页面
│       ├── dashboard.py       #     仪表盘
│       ├── upload_run.py      #     上传 + 配置 + 执行 + Agent 交接
│       ├── results.py         #     结果浏览 + Agent 修复展示
│       ├── history.py         #     运行历史
│       └── compare.py         #     运行对比
├── .claude/
│   ├── settings.json          #   项目 hooks
│   └── skills/
│       ├── structtable-workspace/  # 工作区管理（Agent）
│       ├── structtable-run/        # 执行管线 llm_direct（Agent 调 CLI）
│       ├── structtable-codegen/    # 读表→写代码→执行（纯 Agent）
│       └── structtable-verify/     # 质量检验 + 自动补全（纯 Agent）
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

## 常用命令

```bash
# 安装
pip install -e .
pip install -e ".[ocr]"      # OCR_VL 需要 PyMuPDF
pip install -e ".[ui]"       # Web UI（Streamlit）

# 配置
cp .env.example .env          # 填入 LLM_API_KEY 和 MINERU_TOKEN

# === Web UI（可视化交互） ===
streamlit run app/main.py --server.port 8501

# === Agent Skill（智能处理） ===
# /structtable-workspace upload <file.pdf>
# /structtable-workspace list / compare / clean
# /structtable-run <file> --project <名>
# /structtable-codegen <run_id>
# /structtable-verify [run_id]
```

## Web UI + Agent 协作模式

```
Web UI (Streamlit)                 Claude Code Agent
   │                                     │
   ├─ 上传 PDF                           │
   ├─ 选转换引擎                          │
   ├─ 执行 llm_direct ──────▶ workspace/  │
   ├─ 显示结果                           │
   ├─ "Agent 可做:                        │
   │   /structtable-verify <id> 校验" ──▶ 读 Markdown + JSON
   │   "/structtable-codegen <id> 省钱" ─▶ 读表→写代码→执行
   │                                     ├─ 处理完成
   │                                     ├─ 回写 verified/ 或 codegen/
   │  ◀────────────────────────────── done
   ├─ 刷新 → 查看 Agent 处理结果          │
   └─ 导出                               │
```

- **Web UI 负责**: 上传、选引擎、跑 `llm_direct`、可视化、对比
- **Agent 负责**: `llm_codegen`（写代码提取）、`verify`（智能校验补全）
- **共享**: `workspace/` 是两者之间的数据总线

## Agent Skills

| Skill | 触发方式 | 职责 | 执行者 |
|-------|---------|------|--------|
| `structtable-workspace` | `/structtable-workspace <upload\|list\|compare\|clean>` | 管理工作区 | Agent |
| `structtable-run` | `/structtable-run [文件] --project <名>` | 交互引导 + 执行管线 | Agent 调 CLI |
| `structtable-codegen` | `/structtable-codegen <run_id>` | 读表→写代码→执行→校验 | **纯 Agent** |
| `structtable-verify` | `/structtable-verify [run_id]` | 6 类检测 + ≤10% 自动补全 | **纯 Agent** |

## 核心设计决策

### LLM 提取的设计要点

- **无预设 schema**: System prompt 描述通用表格规则，LLM 自行从 HTML 发现字段名
- **并发控制**: `LLM_WORKERS`（默认 5）个线程并行提取不同 section
- **API 兼容**: OpenAI 兼容的 `/chat/completions` 端点
- **JSON 解析容错**: 四级回退 — 直接解析 → code block 提取 → 最外层括号 → 任意括号组
- **零 ID 重试**: 输出不含编号但 HTML 含编号列时，自动重试一次

### 配置分组

| 分组 | 关键变量 | 用途 |
|------|---------|------|
| LLM | `LLM_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_WORKERS` | 提取模型 |
| CONVERTER | `CONVERTER` | `ocr_vl` / `mineru` |
| OCR | `OCR_URL`, `OCR_DPI` | OCR_VL 路径 |
| MinerU | `MINERU_TOKEN`, `MINERU_MODEL_VERSION` | MinerU 路径 |
