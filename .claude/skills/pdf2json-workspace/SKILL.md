---
name: pdf2json-workspace
description: 管理 PDF2json 工作区——上传文件、浏览运行记录、对比结果、清理旧数据。首次使用自动初始化工作区目录。
---

# PDF2json Workspace — 工作区管理

管理 `workspace/` 目录中的运行时数据。工作区与代码完全隔离（gitignore）。

## 触发条件

- 用户说"管理工作区" / "上传 PDF" / "查看运行记录" / "对比结果" / "清理 workspace"
- `/pdf2json-workspace <子命令>`
- `/pdf2json-run` 执行前自动调用 upload 子命令

## 路径约定

项目根 = 当前工作目录。所有命令在项目根下执行。
`workspace/` 目录在项目根下，首次运行自动创建。

---

## 子命令总览

| 子命令 | 用法 | 功能 |
|--------|------|------|
| `upload` | `upload <file.pdf> [--project <名>]` | 上传 PDF 到工作区 |
| `list` | `list [--limit 20]` | 列出所有运行记录 |
| `status` | `status <run_id>` | 查看某次运行的详细信息 |
| `compare` | `compare <run_a> <run_b>` | 对比两次运行 |
| `clean` | `clean --keep 10` 或 `--older-than 7d` | 清理旧运行 |

---

## init — 首次初始化

**在执行任何子命令之前，先检测 workspace/ 是否存在。** 如果不存在，自动创建：

```bash
mkdir -p workspace/uploads workspace/runs
echo "✅ workspace/ 已初始化"
```

告知用户：
> "工作区目录已创建。上传的 PDF 将保存在 `workspace/uploads/`，每次运行的结果保存在 `workspace/runs/`。这些文件不会被 git 跟踪。"

---

## upload — 上传 PDF

**交互式流程**：

1. 如果用户未指定文件路径，用 AskUserQuestion 引导：
   > "请提供 PDF 文件路径，或将文件拖入对话框。"

2. 如果用户未指定项目名，从文件名推断并确认：
   > "项目名自动推断为 **{推断的项目名}**。使用此名称？"

3. 执行：
   ```bash
   mkdir -p "workspace/uploads/<项目名>/"
   cp "<源PDF路径>" "workspace/uploads/<项目名>/"
   ```

4. 验证：
   ```bash
   ls -lh "workspace/uploads/<项目名>/<文件名>"
   ```

5. 告知用户：
   > "✅ **{filename}** ({size} KB) 已上传到 `workspace/uploads/{项目名}/`"

6. **自动引导下一步**，用 AskUserQuestion：
   > "PDF 已就绪。是否现在运行提取管线？"
   > 选项：A) 是，开始提取    B) 稍后再处理

如果用户选 A，自动触发 `/pdf2json-run` 流程。

---

## list — 列出运行记录

```bash
python -c "
import json, os

runs_dir = 'workspace/runs'
if not os.path.exists(runs_dir):
    print('（空 — 还没有运行记录）')
    exit()

runs = sorted(
    [(d, os.path.getmtime(f'{runs_dir}/{d}')) for d in os.listdir(runs_dir) if os.path.isdir(f'{runs_dir}/{d}')],
    key=lambda x: x[1], reverse=True
)

print(f'workspace/runs/ ({len(runs)} 条记录)')
print(f'{\"状态\":4} {\"运行时间\":20} {\"项目\":20} {\"条目\":6} {\"已验证\":4}')
print('─' * 64)

for run_dir, mtime in runs[:30]:
    rj = f'{runs_dir}/{run_dir}/run.json'
    meta = {}
    if os.path.exists(rj):
        meta = json.load(open(rj, encoding='utf-8'))
    status = meta.get('status', '?')
    icon = {'running':'⏳','extracted':'✅','completed':'✅','needs_review':'⚠️','failed':'❌'}.get(status, '⬜')
    project = meta.get('project', '?')[:18]
    created = meta.get('created', '')[:16]
    total = meta.get('results', {}).get('total_items', '?')
    verified = '✅' if meta.get('results', {}).get('verified') else '❌'
    print(f'{icon:2} {created:18} {project:20} {str(total):>5}  {verified}')
"
```

**如果 list 为空**，告知用户：
> "📂 工作区还没有运行记录。上传 PDF 并执行提取管线即可开始。"

---

## status — 查看运行详情

```bash
python -c "
import json, os
run_dir = 'workspace/runs/<run_id>'
if not os.path.exists(run_dir):
    print('运行不存在')
    exit()
rj = f'{run_dir}/run.json'
meta = json.load(open(rj, encoding='utf-8'))
print(json.dumps(meta, ensure_ascii=False, indent=2))
"
```

以表格形式展示给用户：输入文件、配置（converter、backend、model）、结果统计（条目数、错误率、修复数）、时间线。

---

## compare — 对比两次运行

1. 如果用户未指定 run_id，先用 list 展示，让用户选择两个 run。
2. 用 AskUserQuestion：
   > "选择要对比的两次运行：运行 A 和运行 B"

3. 对比维度：
   - 条目总数差异
   - ID 覆盖差异（哪些 ID 仅在一方出现）
   - 校验错误率对比
   - 提取耗时对比

4. 输出对比表。

---

## clean — 清理旧运行

**清理前必须确认**。用 AskUserQuestion：
> "将删除以下 {N} 条运行记录：\n{列表}\n\n确认删除？"

选项：
- "确认删除"
- "取消"

支持的清理策略：
```bash
# 保留最近 N 条
python -c "
import os, shutil
runs = sorted(
    [d for d in os.listdir('workspace/runs') if os.path.isdir(f'workspace/runs/{d}')],
    key=lambda d: os.path.getmtime(f'workspace/runs/{d}'), reverse=True
)
for r in runs[10:]:  # keep 10
    shutil.rmtree(f'workspace/runs/{r}')
    print(f'  deleted: {r}')
"

# 删除失败运行
python -c "
import os, shutil, json
for d in os.listdir('workspace/runs'):
    p = f'workspace/runs/{d}'
    if not os.path.isdir(p): continue
    rj = f'{p}/run.json'
    if os.path.exists(rj):
        if json.load(open(rj)).get('status') == 'failed':
            shutil.rmtree(p)
            print(f'  deleted failed: {d}')
"
```
