---
name: structtable-run
description: 执行 PDF 表格数据 → 结构化 JSON 的完整代码管线。自动检测环境、引导用户选择配置、执行提取。
---

# StructTable Run — 交互式代码管线

将 PDF 中的表格数据转换为结构化 JSON。首次运行自动引导设置，每次运行前让用户确认配置。

## 触发条件

- 用户说"提取 PDF 表格" / "转换 PDF 到 JSON" / "结构化 PDF 数据"
- 用户提供了一个 PDF 或 Markdown 文件路径
- 用户在 `/structtable-workspace upload` 之后自然接续

## 重要：路径约定

本项目所有路径均为相对于项目根目录。项目根目录 = 包含 `pipeline/` 和 `workspace/` 的目录。

---

## Phase 0: 首次运行检测

### 0a. 检测 .env
```bash
test -f .env && echo "EXISTS" || echo "MISSING"
```
如果 MISSING，用 AskUserQuestion 引导创建。

### 0b. 检测 workspace/
```bash
test -d workspace && echo "EXISTS" || echo "MISSING"
```
如果 MISSING：`mkdir -p workspace/uploads workspace/runs`

### 0c. 检测依赖
```bash
python -c "import bs4, requests, dotenv; print('OK')" 2>&1
```
如果失败：`pip install -e .`

---

## Phase 1: 交互式确认配置

用 AskUserQuestion 引导用户确认。不要跳过。

### 问题 1：输入文件
如果用户已指定，跳过。

### 问题 2：PDF 转换引擎
> A. MinerU（推荐）— 云端 API
> B. OCR_VL — 自托管 VLM 服务

### 问题 3：项目名称
从文件名自动推断，允许修改。

### 问题 4：提取方式
> A. LLM 直接提取（默认）
> B. 稍后用 `/structtable-codegen`（省钱）

---

## Phase 2: 执行管线

```bash
# Step 1: 上传 PDF
mkdir -p "workspace/uploads/<项目名>/"
cp "<源PDF路径>" "workspace/uploads/<项目名>/"

# Step 2: 创建 run 目录
RUN_DIR="workspace/runs/$(date +%Y%m%d_%H%M)_<项目>_<converter>_<backend>"
mkdir -p "$RUN_DIR"/{markdown,extracted,verified,codegen,reports,logs}

# Step 3: 写 run.json（初始状态）

# Step 4: PDF → Markdown
python -m pipeline.main convert "<pdf>" --converter <conv> --output "$RUN_DIR/extracted/temp.json"
mv "workspace/uploads/<项目>/*.md" "$RUN_DIR/markdown/"

# Step 5: Markdown → JSON
python -m pipeline.main convert "$RUN_DIR/markdown/<file>.md" --output "$RUN_DIR/extracted/<file>.json"

# Step 6: 更新 run.json（统计条目数，status="extracted"）
```

---

## Phase 3: 输出并引导下一步

```
✅ 管线执行完成

📁 Run ID: <run_id>
📊 提取结果: <N> 条

🤖 建议下一步:
   /structtable-verify <run_id>  — 智能校验数据质量
   /structtable-codegen <run_id> — 用代码提取（省钱）
```

---

## 错误处理

| 错误 | 话术 |
|------|------|
| MinerU 超时 | "MinerU 处理超时。可重试或切换到 OCR_VL" |
| MinerU token 无效 | "MinerU token 被拒绝。请更新 .env 中的 MINERU_TOKEN" |
| LLM API 异常 | "请检查 .env 中的 LLM_URL 和 LLM_API_KEY" |
| 依赖缺失 | "缺少依赖。运行 pip install -e ." |
