# -*- coding: utf-8 -*-
"""查询章节规划与卷纲（只读）。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
cur = db.cursor()

for t in ("webnovel_chapter_plans", "webnovel_chapter_plan", "webnovel_volume_outline", "webnovel_volumes", "webnovel_chapter_meta"):
    try:
        cur.execute(f"PRAGMA table_info({t})")
        cols = [c[1] for c in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        n = cur.fetchone()[0]
        print(f"\n[{t}] count={n} cols={cols}")
        cur.execute(f"SELECT * FROM {t} LIMIT 3")
        for r in cur.fetchall():
            print(r)
    except Exception as e:
        print(t, "ERR", e)

db.close()
