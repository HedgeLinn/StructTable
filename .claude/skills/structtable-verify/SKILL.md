---
name: structtable-verify
description: 检验 StructTable 提取结果完整性。自动对比原始 Markdown 修复遗漏数据。错误率<10%自动补全，≥10%生成报告。
---

# StructTable Verify — 质量检验与自动补全

对比原始 Markdown（可靠源）与提取的 JSON，逐条校验并自动修复。

## 触发条件
- /structtable-run 完成后用户确认
- 用户说"检查提取质量" / "验证数据完整性" / "补全缺失数据"
- /structtable-verify [run_id]

## Phase 1: 加载数据
读取 extracted/*.json + markdown/*.md

## Phase 2: 六类问题检测
Agent 亲自交叉校验:

1. 续表孤立 — 相同 ID 出现多次，其中一个数据为空 → 合并
2. 规格=ID 错误 — 规格字段填入编号 → 从 Markdown 表头修正
3. 数值合计不匹配 — 主值≠子项和 → 从 Markdown 读取正确值
4. 重复条目 — 完全相同 → 去重
5. 单位格式错误 — 空值或含噪声 → 从上下文修正
6. 章节归属异常 — 数据错归或漏提 → 修正归属

## Phase 3: 错误率计算
affected / total → ≤10% 自动补全，>10% 生成报告

## Phase 4: 修复输出
每条修复记录 _fix_log (action, original_value, corrected_value, evidence, confidence)
confidence=low 的不修，标记 _unresolved
保存到 workspace/runs/<run_id>/verified/
更新 run.json
