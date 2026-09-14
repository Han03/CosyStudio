# -*- coding: utf-8 -*-
"""验证 script_writing_tasks.polished 的存储形态（task 204 及最近几条）"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
cur = db.cursor()
rows = cur.execute(
    "SELECT id, chapter_index, status, polished FROM script_writing_tasks "
    "WHERE id >= 200 ORDER BY id"
).fetchall()
db.close()

for rid, ch, st, polished in rows:
    if not polished:
        print(f"#{rid} ch{ch} {st}: polished 空")
        continue
    literal_n = polished.count("\\n")   # 字面反斜杠+n
    real_n = polished.count("\n")       # 真实换行
    print(
        f"#{rid} ch{ch} {st}: len={len(polished)} 字面\\n={literal_n} 真实换行={real_n} | 开头={repr(polished[:60])}"
    )
