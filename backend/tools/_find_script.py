# -*- coding: utf-8 -*-
"""查询剧本与章节数据（只读）。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
cur = db.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]

# 剧本表
for t in tables:
    if "script" in t.lower() or "project" in t.lower():
        try:
            cur.execute(f"PRAGMA table_info({t})")
            cols = [c[1] for c in cur.fetchall()]
            print(f"\n[{t}] cols={cols}")
        except Exception as e:
            print(t, "ERR", e)

# 剧本列表
for t in ("scripts", "webnovel_project", "webnovel_projects"):
    if t in tables:
        try:
            cur.execute(f"SELECT * FROM {t} LIMIT 10")
            rows = cur.fetchall()
            print(f"\n== {t} ({len(rows)} shown) ==")
            for r in rows:
                print(r)
        except Exception as e:
            print(t, "ERR", e)

# 章节
for t in tables:
    if "chapter" in t.lower() and "plan" not in t.lower():
        try:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            n = cur.fetchone()[0]
            print(f"\n[{t}] count={n}")
        except Exception:
            pass

db.close()
