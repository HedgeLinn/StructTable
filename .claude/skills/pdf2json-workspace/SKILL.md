---
name: pdf2json-workspace
description: 管理 PDF2json 工作区——上传文件、浏览运行记录、对比结果、清理旧数据。当用户提到"管理工作区"、"上传PDF"、"查看运行记录"、"对比结果"、"清理workspace"时触发。
---

# PDF2json Workspace — 工作区管理

管理 `workspace/` 目录中的所有运行时数据。工作区与代码完全隔离，不进 git。

## 工作区结构

```
workspace/
├── uploads/                    # 用户上传的原始 PDF
│   └── <项目名>/
│       └── *.pdf
│
└── runs/                       # 每次运行的完整产物
    └── <YYYYMMDD_HHMM_<项目名>_<converter>_<backend>/
        ├── run.json            # 运行元数据
        ├── markdown/           # PDF 转换结果 (.md)
        ├── extracted/          # LLM 提取的原始 JSON
        ├── verified/           # Agent 验证+补全后的 JSON
        ├── reports/            # 质量报告
        └── logs/               # 运行日志 (run.log)
```

## 子命令

### `upload` — 上传 PDF 到工作区

```
/pdf2json-workspace upload <file.pdf> [--project <名称>]
```

- 如果未指定 `--project`，从 PDF 文件名自动推断（去掉扩展名，截断到 20 字）
- 复制 PDF 到 `workspace/uploads/<项目名>/`
- 如果文件已存在，询问是否覆盖

### `list` — 列出运行记录

```
/pdf2json-workspace list [--limit 20]
```

输出：

```
workspace/runs/ (3 runs)
────────────────────────────────────────────────────────────
  状态   运行时间           项目             转换器   条目数   已验证
  ✅     2026-06-27 14:30   退役管道第一册   mineru   144      ✅
  ✅     2026-06-27 15:10   退役管道第一册   ocr_vl   138      ❌
  ❌     2026-06-27 16:00   测试集v2          mineru   48       ✅
────────────────────────────────────────────────────────────
```

### `status` — 查看某次运行的详细状态

```
/pdf2json-workspace status <run_id>
```

读取 `run.json` 并展示完整的输入、配置、结果、问题分布。

### `compare` — 对比两次运行

```
/pdf2json-workspace compare <run_id_1> <run_id_2>
```

对比：
- 条目总数差异
- ID 覆盖差异（哪些 ID 只在一次运行中出现）
- 校验错误率对比
- 费用不匹配条目数对比

### `clean` — 清理旧运行

```
/pdf2json-workspace clean --keep 10          # 保留最近 10 次
/pdf2json-workspace clean --older-than 7d    # 删除 7 天前的
/pdf2json-workspace clean --status failed    # 只删除失败的运行
```

清理前必须确认，列出将要删除的目录。

## 实现细节

### 创建 run 目录（由 pdf2json-run 调用）

```python
from datetime import datetime
run_name = f"{datetime.now().strftime('%Y%m%d_%H%M')}_{project}_{converter}_{backend}"
run_dir = f"workspace/runs/{run_name}"
os.makedirs(f"{run_dir}/markdown", exist_ok=True)
os.makedirs(f"{run_dir}/extracted", exist_ok=True)
os.makedirs(f"{run_dir}/verified", exist_ok=True)
os.makedirs(f"{run_dir}/reports", exist_ok=True)
os.makedirs(f"{run_dir}/logs", exist_ok=True)
```

### run.json 模板

```json
{
  "run_id": "20260627_1430_退役管道第一册_mineru_llmdirect",
  "project": "退役管道第一册",
  "created": "2026-06-27T14:30:00",
  "status": "running",
  "input": {
    "pdf": "workspace/uploads/退役管道第一册/定额表第一册.pdf",
    "pages": null,
    "size_bytes": null
  },
  "config": {
    "converter": "mineru",
    "backend": "llm_direct",
    "model": null
  },
  "results": {
    "total_items": null,
    "items_with_id": null,
    "validation_warnings": null,
    "validation_errors": null,
    "orphans_reattached": null,
    "verified": false,
    "fixed_count": null,
    "unresolved_count": null
  },
  "timing": {
    "started": null,
    "pdf_conversion_done": null,
    "extraction_done": null,
    "verification_done": null
  }
}
```

## 关键文件路径

| 文件 | 路径 |
|------|------|
| 工作区根 | `workspace/` |
| 上传目录 | `workspace/uploads/` |
| 运行记录 | `workspace/runs/` |
| 项目根 | `E:/vscode_project/PDF2json/structural_PDF` |
