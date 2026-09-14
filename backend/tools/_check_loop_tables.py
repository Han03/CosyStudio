# -*- coding: utf-8 -*-
"""查伏笔/循环/钩子相关表。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
cur = db.cursor()
tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' "
    "AND (name LIKE '%foreshadow%' OR name LIKE '%loop%' OR name LIKE '%hook%')").fetchall()]
print("相关表:", tables)
for t in tables:
    try:
        n = cur.execute(f"SELECT COUNT(*) FROM {t} WHERE project_id=93").fetchone()[0]
        print(f"  {t}: {n} 条")
    except Exception as e:
        print(f"  {t}: {e}")
db.close()
