# -*- coding: utf-8 -*-
"""扫描 script_writing_tasks 所有记录的 draft/polished 字面换行污染"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
cur = db.cursor()
rows = cur.execute(
    "SELECT id, chapter_index, status, task_type, length(draft), draft, length(polished), polished "
    "FROM script_writing_tasks ORDER BY id"
).fetchall()

print("=== 字面\\n 污染检测（draft/polished） ===")
dirty = []
for r in rows:
    rid, ch, st, tt, dlen, draft, plen, polished = r
    for fname, val in (("draft", draft), ("polished", polished)):
        if not val:
            continue
        lit = val.count("\\n")
        real = val.count("\n")
        if lit > 0 and real == 0:
            dirty.append((rid, ch, fname, len(val), lit))
            print(f"  [脏] #{rid} ch{ch} {fname}: len={len(val)} 字面\\n={lit} 真实换行=0")
        elif lit > 0 and real > 0:
            print(f"  [混合] #{rid} ch{ch} {fname}: len={len(val)} 字面\\n={lit} 真实换行={real}")

print(f"\n共 {len(dirty)} 处需修复")
db.close()
