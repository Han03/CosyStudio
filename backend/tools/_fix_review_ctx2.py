# -*- coding: utf-8 -*-
"""draft_reviewer 调用点补传 word_cfg。"""
p = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\draft_reviewer_executor.py"
with open(p, encoding="utf-8") as f:
    t = f.read()
old = "review_result = await self._review_draft(current_draft, step_ctx, project_id)"
new = 'review_result = await self._review_draft(current_draft, step_ctx, project_id, context.get("word_config") or {})'
if old not in t:
    raise SystemExit("调用点未找到")
t = t.replace(old, new, 1)
with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(t)
print("[OK] 调用点已补传 word_cfg")
