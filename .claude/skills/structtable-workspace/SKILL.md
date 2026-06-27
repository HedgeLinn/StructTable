---
name: structtable-workspace
description: 管理 StructTable 工作区——上传文件、浏览运行记录、对比结果、清理旧数据。首次使用自动初始化工作区目录。
---

# StructTable Workspace

管理 workspace/ 目录中的运行时数据。工作区与代码完全隔离（gitignore）。

## 触发条件
- 用户说"管理工作区" / "上传 PDF" / "查看运行记录" / "对比结果" / "清理 workspace"
- /structtable-workspace <子命令>

## 子命令
| 命令 | 用法 | 功能 |
|------|------|------|
| upload | upload <file.pdf> [--project <名>] | 上传 PDF 到工作区 |
| list | list [--limit 20] | 列出所有运行记录 |
| status | status <run_id> | 查看运行详情 |
| compare | compare <run_a> <run_b> | 对比两次运行 |
| clean | clean --keep 10 或 --older-than 7d | 清理旧运行（需确认） |

## init — 首次初始化
检测 workspace/ 是否存在，不存在则自动创建:
mkdir -p workspace/uploads workspace/runs

## upload 流程
1. 引导用户提供文件路径
2. 从文件名推断项目名，让用户确认
3. 复制到 workspace/uploads/<项目名>/
4. 自动建议下一步: /structtable-run

## list / compare / clean
参考 workspace/runs/ 下的 run.json 元数据操作。
清理前必须用 AskUserQuestion 确认。
