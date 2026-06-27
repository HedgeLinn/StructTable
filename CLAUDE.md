# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🚀 新用户入口（Claude 打开项目后，首先执行此流程）

当你（Claude Code Agent）首次在此项目中响应新用户时，请按以下顺序引导：

### 1. 欢迎与概述
向用户简要介绍："这是 **PDF2json**——将工程预算定额 PDF 转换为结构化 JSON 的工具。支持两种 PDF 转换器（MinerU 云端 / OCR_VL 本地）和两种提取后端（LLM 逐表 / LLM 生成代码）。"

### 2. 检测项目状态
```bash
echo "=== PDF2json 状态检测 ==="
test -f .env && echo "✅ .env 已配置" || echo "⚠️ .env 未配置 — 需要设置 LLM API"
test -d workspace && echo "✅ workspace/ 已就绪" || echo "⚠️ workspace/ 待初始化"
python -c "import bs4, requests, dotenv; print('✅ 核心依赖已安装')" 2>&1 || echo "⚠️ 依赖缺失 — pip install -e ."
```

### 3. 交互式引导
根据检测结果，用 AskUserQuestion 引导用户完成缺失步骤。参考 `.claude/skills/pdf2json-run/SKILL.md` 中的 Phase 0 流程。

### 4. 技能推荐
根据用户意图推荐合适的 Skill：
- 用户想提取 PDF → 建议 `/pdf2json-workspace upload` → `/pdf2json-run`
- 用户想检查数据质量 → 建议 `/pdf2json-verify`
- 用户想管理工作区 → 建议 `/pdf2json-workspace list` / `clean`

### 5. 三条核心规则
1. **所有路径相对于项目根目录**（包含 `pipeline/` 的目录），不要使用绝对路径
2. **重要操作前必须和用户确认**（删除运行、选择转换器、覆盖已有结果）
3. **每个阶段完成后，主动建议下一步**（上传→运行→验证→导出）

---

## 项目概述

将工程预算定额 PDF 转换为结构化 JSON。支持两种提取后端，覆盖不同成本/质量场景。

## 完整架构

```
                          PDF
                           │
              ┌────────────┴────────────┐
              │   CONVERTER 选择         │
              ├─────────────────────────┤
              │ mineru (推荐) │ ocr_vl   │
              │ 云端异步 API  │ VLM逐页  │
              │ 干净GFM表格   │ HTML表格  │
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
              │   TABLE TYPE DISCOVERY  │  ← 新增：特征提取 + 聚类
              │   用户确认表类型         │
              └────────────┬────────────┘
                           │
              ┌────────────┴────────────┐
              │   BACKEND 选择           │
              ├───────────┬─────────────┤
              │ llm_direct│ llm_codegen │
              │ (Web UI✅)│ (Agent Only)│
              │ CLI 调API │ Claude读表   │
              │ N次LLM调用│ →写代码→执行 │
              │ 语义容错   │ 确定性高     │
              └───────────┴─┬───────────┘
                          │
                    结构化 JSON
                          │
              ┌───────────┴───────────┐
              │   QUALITY GATE        │  ← 新增
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
          │ 自动补全 │   │ (llm_codegen │
          │ (skill)  │   │  重新生成)  │
          └───────┬──┘   │ 或人工介入   │
                  │      └──────┬───────┘
                  └──────┬──────┘
                         │
                   最终 JSON (含 _fix_log)
```

## 两条 PDF 转换路径

| | MinerU | OCR_VL |
|---|---|---|
| 命令 | `--converter mineru` | `--converter ocr_vl` (默认) |
| 原理 | 云端异步批处理 API | 逐页调用 VLM HTTP API |
| 输出质量 | 干净 GFM 管道表格，材料行天然分离 | HTML 表格，合并单元格可能有误 |
| 后处理 | 无需 | 需 postprocess.py (ODL 融合修复) |
| 依赖 | 仅 API token | PyMuPDF + OCR_VL 服务 |
| 适用 | **推荐首选** | MinerU 不可用时 |

## 两条提取后端

| | `llm_direct` | `llm_codegen` |
|---|---|---|
| **谁执行** | pipeline 代码调 LLM API | **Claude Agent 亲自读表→写代码→执行** |
| **Web UI 支持** | ✅ `上传与运行` | ❌ Web UI 无法替代 Agent 推理 |
| **Agent Skill** | `/pdf2json-run` 调用 CLI | `/pdf2json-codegen` |
| **LLM 调用次数** | N 次（每表一次） | **1 次**（生成代码） |
| **确定性** | 低（API 返回有方差） | 高（代码逻辑确定） |
| **HTML 噪声容忍** | 高（语义理解容错） | 较低（代码机械执行） |
| **可复用** | 否 | 是（代码可沉淀到 workspace） |
| **适用** | 本地大模型 (不在意 token) | 云端 API (token 敏感) |

> **关键区分**：`llm_codegen` 不是 pipeline 代码功能，是 Agent Skill。只有 Claude 的推理能力能读表→写代码→执行→校验。

## 已知数据丢失模式（Agent 自动补全需处理的 6 类问题）

从 38 页样本 PDF 的真实运行结果中识别：

| # | 问题类别 | 根因 | 检测方法 | Agent 可修? |
|---|---------|------|---------|:---:|
| 1 | **续表孤立** — 跨页表格被提取为两个独立条目（其中一个基价=0、明细为空） | 分页截断 | 相同 ID 出现多次 + 其中一个基价=0 | ✅ |
| 2 | **规格=ID 错误** — 规格字段填入了定额编号（"9-25" 而非 "DN300"） | 续表缺规格行，LLM 猜测错误 | 规格值匹配 `\d+-\d+` 模式 | ✅ |
| 3 | **费用合计不匹配** — 基价 ≠ 人工费+材料费+机械费 | OCR 列偏移 | `abs(基价 - sum(费用构成)) > 1.0` | ✅ |
| 4 | **重复条目** — 同一 ID 出现两次完全相同的条目 | 大表 chunk 拆分重叠 | 相同 ID + 相同内容 hash | ❌ 代码去重 |
| 5 | **计量单位格式错误** — 值为 `\| \| \|` 或空 | OCR 读入管道符 | 空值或含 `\|` 字符 | ✅ |
| 6 | **章节归属错误** — 表格数据被归入错误的章节 | document_parser 正则匹配错误 | h2 与实际内容不匹配 | ⚠️ 部分 |

Agent 自动补全的核心原则：**对比原始 Markdown（可靠源）与提取的 JSON，逐条校验修正**。

## 工作区架构（运行时隔离）

所有运行时数据（上传、产物、日志）存入 `workspace/`，与代码完全分离。`workspace/` 在 `.gitignore` 中，不进 git。

```
workspace/
├── uploads/                              # 用户上传的原始 PDF
│   └── <项目名>/
│       └── *.pdf
│
└── runs/                                 # 每次运行的完整产物
    └── <YYYYMMDD_HHMM_<项目>_<converter>_<backend>/
        ├── run.json                      # 运行元数据（配置、统计、状态）
        ├── markdown/                     # MinerU/OCR_VL 转换结果
        ├── extracted/                    # LLM 提取的原始 JSON
        ├── verified/                     # Agent 验证+补全后的 JSON
        ├── reports/                      # 质量报告
        └── logs/                         # 运行日志
```

## 项目结构

```
structural_PDF/
├── pipeline/                  # Python 主包（代码，git 跟踪）
│   ├── main.py                # CLI 入口 (convert / batch / validate)
│   ├── config.py              # 环境变量配置（从 .env 读取）
│   ├── document_parser.py     # Markdown 章节切分 + HTML table 提取
│   ├── llm_extractor.py       # llm_direct 后端：LLM 逐表提取引擎
│   │                          #   - 续表识别合并 (_merge_table_groups)
│   │                          #   - Token 估计与大表拆分 (_split_large_html)
│   │                          #   - 孤立条目归附 (_post_process)
│   │                          #   - 异常输出自动重试 + 健康监控面板
│   ├── postprocess.py         # OCR_VL 路径专用：两阶段 HTML 修复
│   ├── utils.py               # 数值解析、JSON 格式化、多策略名称拆分、校验
│   └── pdf2markdown/          # PDF→Markdown 转换器适配器
│       ├── base.py            #   ConverterAdapter ABC
│       ├── mineru.py          #   MinerU 云端适配器
│       ├── ocr_vl.py          #   OCR_VL HTTP API 适配器
│       └── batch_convert.py   #   批量转换脚本
├── workspace/                 # 运行时工作区（gitignore，不进仓库）
│   ├── uploads/               #   用户上传的 PDF
│   └── runs/                  #   每次管线的完整产物
├── .claude/
│   ├── settings.json            #   项目 hooks（管线完成 → 建议 verify）
│   └── skills/
│       ├── pdf2json-workspace/  # Skill: 工作区管理（Agent）
│       ├── pdf2json-run/        # Skill: 执行管线 llm_direct（Agent 调 CLI）
│       ├── pdf2json-codegen/    # Skill: 读表→写代码→执行（纯 Agent）
│       └── pdf2json-verify/     # Skill: 质量检验 + 自动补全（纯 Agent）
├── app/                         # Web UI（Streamlit 前端）
│   ├── main.py                  #   入口 + 侧边栏导航
│   ├── utils.py                 #   工作区扫描、run 读写
│   └── pages/                   #   功能页面
│       ├── dashboard.py         #     仪表盘
│       ├── upload_run.py        #     上传 + 配置 + 执行 + Agent 交接
│       ├── results.py           #     结果浏览 + Agent 修复展示
│       ├── history.py           #     运行历史
│       └── compare.py           #     运行对比
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
# 页面: 仪表盘 / 上传运行 / 结果浏览 / 历史 / 对比
# 管线完成后提示用户到 Claude Code 运行 /pdf2json-verify

# === Agent Skill（智能校验） ===
# /pdf2json-workspace upload <file.pdf>   — 上传到工作区
# /pdf2json-workspace list                — 列出运行记录
# /pdf2json-run <file> --project <名>     — 完整管线
# /pdf2json-verify [run_id]               — 质量检验 + 自动补全

# === 或直接调 CLI ===
# 单文件转换
python -m pipeline.main convert input.md --output output.json
python -m pipeline.main convert input.pdf --converter mineru --output output.json

# 批量处理
python -m pipeline.main batch input_dir/ --output output_dir/

# 验证
python -m pipeline.main validate output.json
```

## Web UI + Agent 协作模式

```
Web UI (Streamlit)                 Claude Code Agent
   │                                     │
   ├─ 上传 PDF                           │
   ├─ 选转换器(Mineru/OCR_VL)            │
   ├─ 执行 llm_direct ──────▶ workspace/  │
   ├─ 显示结果                           │
   ├─ "Agent 可做:                        │
   │   /pdf2json-verify <run_id> 校验" ──▶ 读 Markdown + JSON
   │   "/pdf2json-codegen <run_id> 省钱" ─▶ 读表→写代码→执行
   │                                     ├─ 校验/代码生成完成
   │                                     ├─ 回写 verified/ 或 codegen/
   │  ◀────────────────────────────── done
   ├─ 刷新 → 查看 Agent 修复/代码结果    │
   └─ 审核 + 导出                        │
```

- **Web UI 负责**: 上传、选转换器、跑 `llm_direct`、可视化、对比
- **Agent 负责**: `llm_codegen`（写代码提取）、`verify`（智能校验补全）
- **共享**: `workspace/` 是两者之间的数据总线

## Agent Skills

| Skill | 触发方式 | 职责 | 执行者 |
|-------|---------|------|--------|
| `pdf2json-workspace` | `/pdf2json-workspace <upload\|list\|compare\|clean>` | 管理工作区 | Agent |
| `pdf2json-run` | `/pdf2json-run [文件] --project <名>` | 交互引导 + 执行管线 (llm_direct) | Agent 调 CLI |
| `pdf2json-codegen` | `/pdf2json-codegen <run_id>` | 读表→写代码→执行→校验 | **纯 Agent** |
| `pdf2json-verify` | `/pdf2json-verify [run_id]` | 6 类检测 + ≤10% 自动补全 | **纯 Agent** |

调用链：`workspace upload → run（或 codegen）→ verify`。
Web UI 可触发 `llm_direct`，但 `codegen` 和 `verify` 只有 Agent 能做。

## 核心设计决策

### LLM 提取的设计要点

- **无预设 schema**: System prompt 描述通用表格规则（编号列、规格列、费用行、明细段），LLM 自行从 HTML 发现字段名
- **并发控制**: `LLM_WORKERS`（默认 5）个线程并行提取不同 section
- **API 兼容**: OpenAI 兼容的 `/chat/completions` 端点，`extra_body: {"thinking": {"type": "disabled"}}` 确保确定性输出
- **JSON 解析容错**: 四级回退 — 直接解析 → \`\`\`json 块提取 → 最外层括号 → 任意括号组
- **零 ID 重试**: 输出不含编号但 HTML 含"定额编号"时，携带 strict 提示自动重试一次

### 配置分组

| 分组 | 关键变量 | 用途 |
|------|---------|------|
| LLM | `LLM_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_WORKERS` | 提取模型 |
| CONVERTER | `CONVERTER` | `ocr_vl` / `mineru` |
| BACKEND | `BACKEND` | `llm_direct` / `llm_codegen` (新增) |
| OCR | `OCR_URL`, `OCR_DPI` | OCR_VL 路径 |
| MinerU | `MINERU_TOKEN`, `MINERU_MODEL_VERSION`, `MINERU_POLL_MAX` | MinerU 路径 |

### 待实现模块

| 模块 | 职责 | 优先级 |
|------|------|--------|
| Table Type Discovery | 特征提取 + 聚类 → 用户确认表类型 | P0 |
| `llm_codegen` 后端 | LLM 生成提取代码 → 沙箱执行 → 结果校验 | P0 |
| Quality Gate | 准确率/完整率计算 + 10% 阈值分叉 | P0 |
| Agent 自动补全 Skill | 对比 Markdown 与 JSON，自动修复 6 类问题 | P1 |
| 代码模板库 | 已验证的提取代码沉淀，同类型表直接复用 | P2 |
