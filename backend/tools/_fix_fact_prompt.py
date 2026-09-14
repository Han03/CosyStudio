# -*- coding: utf-8 -*-
"""修复 fact_record_prompt.md 单花括号 JSON 示例（.format() 兼容）。"""
import io

p = r"C:\MyProjects\CosyStudio\backend\webnovel\prompts\fact_record_prompt.md"
with io.open(p, "r", encoding="utf-8", newline="") as f:
    text = f.read()

pairs = [
    ('如 {"type": "关系", "character": "李威", "target": "苏婉清", "description": "因路线选择产生激烈冲突，最终因林若兮的调解妥协"}',
     '如 {{"type": "关系", "character": "李威", "target": "苏婉清", "description": "因路线选择产生激烈冲突，最终因林若兮的调解妥协"}}'),
    ('如 {"type": "身份揭露", "alias": "神秘黑袍男人", "real_name": "李岩", "description": "总兵府护卫统领"}',
     '如 {{"type": "身份揭露", "alias": "神秘黑袍男人", "real_name": "李岩", "description": "总兵府护卫统领"}}'),
    ('如 {"type": "成长", "character": "角色名", "description": "成长说明"}',
     '如 {{"type": "成长", "character": "角色名", "description": "成长说明"}}'),
    ('如 {"type": "能力", "character": "角色名", "ability": "能力名", "description": "能力说明"}',
     '如 {{"type": "能力", "character": "角色名", "ability": "能力名", "description": "能力说明"}}'),
]

n = 0
for old, new in pairs:
    if old in text:
        text = text.replace(old, new, 1)
        n += 1
        print("replaced:", old[:45])
    else:
        print("NOT FOUND:", old[:45])

with io.open(p, "w", encoding="utf-8", newline="") as f:
    f.write(text)
print("total replaced:", n)
