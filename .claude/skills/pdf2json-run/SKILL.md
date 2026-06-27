---
name: pdf2json-run
description: 执行 PDF 定额表 → 结构化 JSON 的完整代码管线。自动检测环境、引导用户选择配置、执行提取。
---

# PDF2json Run — 交互式代码管线

将工程预算定额 PDF 转换为结构化 JSON。**首次运行自动引导设置，每次运行前让用户确认配置。**

## 触发条件

- 用户说"提取 PDF" / "转换 PDF 到 JSON" / "结构化预算定额"
- 用户提供了一个 PDF 或 Markdown 文件路径
- 用户在 `/pdf2json-workspace upload` 之后自然接续

## 重要：路径约定

本项目所有路径均为**相对于项目根目录**。项目根目录 = 包含 `pipeline/` 和 `workspace/` 的目录（即 `structural_PDF/`）。

执行任何命令前，先进入项目根：
```bash
cd <项目根目录>   # Claude Code 启动时所在的目录
```

---

## Phase 0: 首次运行检测（必须首先执行）

### 0a. 检测 .env

```bash
test -f .env && echo "EXISTS" || echo "MISSING"
```

**如果 MISSING**，用 AskUserQuestion 询问用户：

> "检测到这是首次运行，缺少 `.env` 配置文件。我需要为你创建它。请提供以下信息（现在只需提供一个可用的 LLM API 配置即可开始）："

询问：
1. LLM API 地址（选项：DeepSeek / 自定义 / 暂时跳过）
2. LLM API Key

然后执行：
```bash
cp .env.example .env
```
并替换 `.env` 中的 `LLM_URL`、`LLM_API_KEY`、`LLM_MODEL`。

如果用户提供了 MinerU token，同时填入 `MINERU_TOKEN` 和 `CONVERTER=mineru`。

### 0b. 检测 workspace/

```bash
test -d workspace && echo "EXISTS" || echo "MISSING"
```

**如果 MISSING**：
```bash
mkdir -p workspace/uploads workspace/runs
echo "workspace/ created"
```

### 0c. 检测依赖

```bash
python -c "import bs4, requests, dotenv; print('OK')" 2>&1
```

**如果失败**：
```bash
pip install -e . && echo "Dependencies installed"
```

---

## Phase 1: 交互式确认配置

在上一步通过后，使用 AskUserQuestion 引导用户确认参数。**不要跳过这一步，即使用户之前运行过。**

### 问题 1：输入文件

如果用户已经指定了 PDF/Markdown 路径，跳过。
否则，询问文件路径或让用户拖入文件。

### 问题 2：PDF 转换器

> "选择 PDF 转换器："

| 选项 | 标签 | 说明 |
|------|------|------|
| A | MinerU（推荐）| 云端 API，表格质量高，需要 MINERU_TOKEN |
| B | OCR_VL | 自托管 VLM 服务，需要 OCR_URL |

如果用户选择 MinerU 但没有 token，提示获取方式（mineru.net → API 管理页面）。

### 问题 3：项目名称

从 PDF 文件名自动推断。如果用户不满意，允许修改。

### 问题 4：提取后端

> "选择提取方式："

| 选项 | 标签 | 说明 |
|------|------|------|
| A | LLM 直接提取（默认）| LLM 逐表提取，语义容错强，适合本地大模型 |
| B | LLM 生成代码（省钱）| 1 次 LLM 调用生成提取代码，适合云端 API |

---

## Phase 2: 执行管线

用户确认后，按以下步骤执行。**每步都要向用户报告进度。**

### Step 1: 上传 PDF

```bash
mkdir -p "workspace/uploads/<项目名>/"
cp "<源PDF路径>" "workspace/uploads/<项目名>/"
```

告知用户：`✅ PDF 已保存到 workspace/uploads/<项目名>/`

### Step 2: 创建 run 目录

```bash
RUN_ID="$(date +%Y%m%d_%H%M)_<项目名>_<converter>_<backend>"
RUN_DIR="workspace/runs/$RUN_ID"
mkdir -p "$RUN_DIR/markdown" "$RUN_DIR/extracted" "$RUN_DIR/verified" "$RUN_DIR/reports" "$RUN_DIR/logs"
```

### Step 3: 写 run.json（初始状态）

```python
import json, os, datetime
run_meta = {
    "run_id": run_id, "project": project, "status": "running",
    "created": datetime.datetime.now().isoformat(),
    "config": {"converter": converter, "backend": backend, "model": os.getenv("LLM_MODEL")},
    "results": {}, "timing": {"started": datetime.datetime.now().isoformat()}
}
with open(f"{run_dir}/run.json", "w", encoding="utf-8") as f:
    json.dump(run_meta, f, ensure_ascii=False, indent=2)
```

### Step 4: PDF → Markdown

```bash
python -m pipeline.main convert "workspace/uploads/<项目>/<file>.pdf" \
  --converter <mineru|ocr_vl> \
  --output "$RUN_DIR/extracted/temp.json"
```

将生成的 `.md` 移到 run 目录：
```bash
mv "workspace/uploads/<项目>/<file>.md" "$RUN_DIR/markdown/" 2>/dev/null
# MinerU 有时输出到其他位置，寻找并移动
find workspace/uploads/<项目>/ -name "*.md" -exec mv {} "$RUN_DIR/markdown/" \; 2>/dev/null
```

### Step 5: Markdown → 结构化 JSON

```bash
python -m pipeline.main convert "$RUN_DIR/markdown/<file>.md" \
  --output "$RUN_DIR/extracted/<file>.json"
```

### Step 6: 更新 run.json

```python
import json
with open(f"{run_dir}/extracted/<file>.json") as f:
    items = json.load(f)
run_meta["results"]["total_items"] = len(items)
run_meta["results"]["items_with_id"] = sum(1 for i in items if any(k in i for k in ('定额编号','清单编码','清单编号','指标编号')))
run_meta["timing"]["extraction_done"] = datetime.datetime.now().isoformat()
run_meta["status"] = "extracted"
with open(f"{run_dir}/run.json", "w", encoding="utf-8") as f:
    json.dump(run_meta, f, ensure_ascii=False, indent=2)
```

---

## Phase 3: 输出结果并引导下一步

```
✅ 管线执行完成

📁 Run ID: <run_id>
📊 提取结果: <N> 条数据
📂 文件位置:
   Markdown: workspace/runs/<run_id>/markdown/
   提取 JSON: workspace/runs/<run_id>/extracted/

🤖 建议下一步: 我来帮你检验数据质量并自动补全遗漏？
   （这将运行 /pdf2json-verify <run_id>）
```

**不要自动运行 verify**，让用户确认。用 AskUserQuestion 询问是否继续。

---

## 错误处理（必须用以下话术告知用户）

| 错误 | 话术 |
|------|------|
| MinerU 超时 | "MinerU 处理超时（>600s）。可能是 PDF 较大或 API 排队。你可以：A) 重试 B) 切换到 OCR_VL" |
| MinerU token 无效 | "MinerU token 被拒绝。请去 mineru.net → API 管理页面 获取有效 token，然后更新 .env 中的 MINERU_TOKEN" |
| LLM API 返回空 | "LLM API 返回异常（HTTP {code}）。请检查 .env 中的 LLM_URL 和 LLM_API_KEY" |
| LLM 502/503 | "LLM 服务暂时不可用。请稍后重试，或更换 .env 中的 LLM_URL" |
| 依赖缺失 | "缺少 Python 依赖。我来帮你安装：pip install -e ." |
| PDF 转换失败 | "PDF 转换失败。是否尝试其他转换器？MinerU ↔ OCR_VL" |
