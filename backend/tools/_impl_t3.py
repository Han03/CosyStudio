# -*- coding: utf-8 -*-
"""T3 剧情审查 schema 说明精简（900→500 字符级，保留全部判定约束）。"""
p = r"C:\MyProjects\CosyStudio\backend\webnovel\prompts\chapter_plot_review_prompt.md"
with open(p, encoding="utf-8") as f:
    t = f.read()

old = '''  【字段说明】
  - score为1-10分，评分锚点：9-10分=该维度无任何值得修改之处；7-8分=合格但存在可改进点；6分及以下=存在必须修正的明显问题。
  - 硬约束：该维度存在severity为medium及以上的问题时，分数不得高于8。
  - worth_revising：该问题是否值得立即修正。仅当问题具体可落地（有明确fix_hint、修改后剧情确实更好）时为true；空泛套话、锦上添花类意见一律标false。severity为critical或high时必须为true。
  - suggestions_actionable：suggestions是否值得在本轮落实到剧情点中；空泛的表扬或笼统建议标false。
  - overall_passed：当且仅当所有维度不存在worth_revising=true的问题、且不存在suggestions_actionable=true的建议时，才为true。
  - 只输出上述JSON对象本身，禁止输出分析过程、解释文字或代码块标记；description每条不超过40字，fix_hint每条不超过30字，suggestions不超过60字。'''
new = '''  【字段说明】
  - score=1-10：9-10无问题；7-8合格可改进；≤6必须修正；存在medium及以上问题时不得高于8。
  - worth_revising：问题可落地（有明确fix_hint）才为true，critical/high必须true；suggestions_actionable：建议值得本轮落实才true；overall_passed：仅当无worth_revising=true问题且无actionable建议时为true。
  - 只输出JSON对象，禁止分析过程/解释/代码块标记；description≤40字，fix_hint≤30字，suggestions≤60字。'''
if old not in t:
    raise SystemExit("字段说明未找到")
t = t.replace(old, new, 1)
with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(t)
print(f"[OK] 字段说明精简：{len(old)} -> {len(new)} 字符（-{len(old)-len(new)}）")
