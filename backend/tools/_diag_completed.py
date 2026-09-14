# -*- coding: utf-8 -*-
"""查所有 completed 任务的 polished 形态"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
cur = db.cursor()
rows = cur.execute(
    "SELECT id, chapter_index, status, length(polished), polished "
    "FROM script_writing_tasks WHERE status='completed' ORDER BY id"
).fetchall()
db.close()

print(f"completed 任务数: {len(rows)}")
for rid, ch, st, plen, polished in rows:
    if not polished:
        print(f"#{rid} ch{ch}: polished 空")
        continue
    literal_n = polished.count("\\n")
    real_n = polished.count("\n")
    print(
        f"#{rid} ch{ch}: len={plen} 字面\\n={literal_n} 真实换行={real_n} | 开头={repr(polished[:50])}"
    )
