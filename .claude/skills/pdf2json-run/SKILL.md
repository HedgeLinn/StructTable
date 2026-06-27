---
name: pdf2json-run
description: 执行 PDF 定额表 → 结构化 JSON 的完整代码管线。当用户需要将工程预算定额 PDF 转换为结构化 JSON 时触发。自动在 workspace/ 下创建运行目录。
---

# PDF2json Run — 代码管线执行

将工程预算定额 PDF 转换为结构化 JSON。所有产物存入 `workspace/runs/<run_id>/`。

## 触发条件

- "转换 PDF 到 JSON" / "提取定额表数据" / "跑 PDF2json 管线"
- 提供了一个 PDF/Markdown 文件路径，要求结构化提取

## 执行流程

```
Step 0: 工作区准备 → 上传文件 + 创建 run 目录 + 写 run.json
Step 1: 环境检查   → 确认依赖和配置就绪
Step 2: PDF 转换    → PDF → Markdown (MinerU 或 OCR_VL)
Step 3: 数据提取    → Markdown → sections → JSON (llm_direct)
Step 4: 输出 + 更新 → 保存 JSON + 更新 run.json + 打印摘要
Step 5: 建议下一步  → 提示运行 /pdf2json-verify
```

---

## Step 0: 工作区准备

### 0a. 确定项目名

- 用户指定了 `--project` → 使用指定值
- 否则从文件名自动推断（去掉扩展名，取前 25 字）

### 0b. 上传 PDF

```
/pdf2json-workspace upload <file.pdf> --project <项目名>
```

实际上直接复制文件：

```bash
# 创建上传目录
mkdir -p workspace/uploads/<项目名>/

# 复制 PDF（如果还没上传过）
cp "<源PDF路径>" "workspace/uploads/<项目名>/"
```

### 0c. 创建 run 目录

```python
from datetime import datetime
run_id = f"{datetime.now().strftime('%Y%m%d_%H%M')}_{project}_{converter}_{backend}"
run_dir = f"workspace/runs/{run_id}"
os.makedirs(f"{run_dir}/markdown", exist_ok=True)
os.makedirs(f"{run_dir}/extracted", exist_ok=True)
os.makedirs(f"{run_dir}/verified", exist_ok=True)
os.makedirs(f"{run_dir}/reports", exist_ok=True)
os.makedirs(f"{run_dir}/logs", exist_ok=True)
```

### 0d. 写 run.json（初始状态）

```python
run_meta = {
    "run_id": run_id,
    "project": project,
    "created": datetime.now().isoformat(),
    "status": "running",
    "input": {
        "pdf": f"workspace/uploads/{project}/{filename}",
        "pages": None,
        "size_bytes": os.path.getsize(pdf_path)
    },
    "config": {
        "converter": converter,
        "backend": backend,
        "model": os.getenv("LLM_MODEL")
    },
    "results": {},
    "timing": {"started": datetime.now().isoformat()}
}
```

---

## Step 1: 环境检查

```bash
cd E:/vscode_project/PDF2json/structural_PDF

# 依赖
python -c "import bs4, requests, dotenv; print('Deps OK')"

# .env
# 如不存在，提示用户从 .env.example 复制并填入 API key
```

---

## Step 2: 转换器和后端选择

| 条件 | 选 converter | 选 backend |
|------|-------------|------------|
| 用户显式指定 | 用指定值 | 用指定值 |
| 默认 | mineru | llm_direct |

---

## Step 3: PDF → Markdown

```bash
python -m pipeline.main convert "workspace/uploads/<项目>/<file>.pdf" \
  --converter {mineru|ocr_vl} \
  --output "workspace/runs/<run_id>/extracted/temp.json"
```

然后将生成的 `.md` 文件移到 `workspace/runs/<run_id>/markdown/`：

```bash
# MinerU 路径会自动输出 .md 到同目录，手动移动
mv "workspace/uploads/<项目>/<file>.md" "workspace/runs/<run_id>/markdown/"
```

更新 run.json：
```python
run_meta["timing"]["pdf_conversion_done"] = datetime.now().isoformat()
```

---

## Step 4: 数据提取

```bash
python -m pipeline.main convert "workspace/runs/<run_id>/markdown/<file>.md" \
  --output "workspace/runs/<run_id>/extracted/<file>.json"
```

监控 LLM 提取进度，关注 Monitor 摘要：
```
Monitor: N sections, X skipped, Y parse errors, Z empty, ...
Output: M items (P with ID, Q other), R orphans reattached
```

更新 run.json：
```python
with open(f"{run_dir}/extracted/<file>.json") as f:
    items = json.load(f)
run_meta["results"]["total_items"] = len(items)
run_meta["results"]["items_with_id"] = sum(1 for i in items if any(k in i for k in ['定额编号','清单编码']))
run_meta["timing"]["extraction_done"] = datetime.now().isoformat()
run_meta["status"] = "extracted"
```

保存 run.json。

---

## Step 5: 输出摘要

```
✅ 管线执行完成

📁 Run ID: 20260627_1430_退役管道第一册_mineru_llmdirect
📄 输入: 定额表第一册.pdf (38页)
📝 Markdown: workspace/runs/<run_id>/markdown/
📊 提取 JSON: workspace/runs/<run_id>/extracted/
   - 总条目: 144
   - 含编号: 144
   - 孤儿: 0

💡 建议下一步: /pdf2json-verify <run_id>
   对结果进行质量检验，错误率<10%将自动补全。
```

---

## 错误恢复

| 错误 | 处理 |
|------|------|
| MinerU 超时 | 询问是否切换 --converter ocr_vl |
| OCR_VL 不可达 | 询问是否切换 --converter mineru |
| LLM API 异常 | 检查 LLM_API_KEY，提示更换端点 |
| 输出 JSON 空 | 建议 --dry-run 查看章节解析 |

## 关键文件路径

| 文件 | 路径 |
|------|------|
| 项目根 | `E:/vscode_project/PDF2json/structural_PDF` |
| 工作区 | `workspace/` |
| 所有 run | `workspace/runs/` |
| 上传区 | `workspace/uploads/` |
| .env | `.env` |
