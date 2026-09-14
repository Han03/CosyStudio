# -*- coding: utf-8 -*-
"""修复 script_writing_tasks 中字面 \\n 污染的 draft/polished 字段。

安全规则：仅当字段"字面\\n>0 且 真实换行=0"时替换（全转义态，无混合风险）。
修复前备份原值到 _fix_backup_escape_20260914.txt。
"""
import sqlite3, json, os

DB = r"C:\MyProjects\CosyStudio\data\cache\app.db"
BACKUP = os.path.join(os.path.dirname(__file__), "_fix_backup_escape_20260914.txt")

db = sqlite3.connect(DB)
cur = db.cursor()
rows = cur.execute(
    "SELECT id, chapter_index, status, task_type, draft, polished "
    "FROM script_writing_tasks ORDER BY id"
).fetchall()

backup = []
fixed = 0
for r in rows:
    rid, ch, st, tt, draft, polished = r
    for fname, val in (("draft", draft), ("polished", polished)):
        if not val:
            continue
        lit = val.count("\\n")
        real = val.count("\n")
        if lit > 0 and real == 0:
            backup.append({"id": rid, "chapter_index": ch, "field": fname, "old": val})
            new_val = val.replace("\\n", "\n")
            cur.execute(f"UPDATE script_writing_tasks SET {fname}=? WHERE id=?", (new_val, rid))
            fixed += 1
            print(f"[修复] #{rid} ch{ch} {fname}: 字面\\n={lit} → 真实换行")

db.commit()
db.close()

with open(BACKUP, "w", encoding="utf-8") as f:
    f.write(json.dumps(backup, ensure_ascii=False, indent=2))
print(f"\n修复 {fixed} 处，备份已存: {BACKUP}")
