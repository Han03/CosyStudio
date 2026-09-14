# -*- coding: utf-8 -*-
"""列出 webnovel 相关表 + 找正文表"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
cur = db.cursor()
rows = cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()
names = [r[0] for r in rows]
print("全部表:", names)
print("\n含 content 字段的表：")
for n in names:
    try:
        cols = [c[1] for c in cur.execute(f"PRAGMA table_info({n})").fetchall()]
        if "content" in cols:
            print(f"  {n}: {cols}")
    except Exception:
        pass
db.close()
