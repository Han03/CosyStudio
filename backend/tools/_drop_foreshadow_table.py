# -*- coding: utf-8 -*-
"""删除 webnovel_foreshadow 表（数据库层）"""
import sqlite3

db_path = r"C:\MyProjects\CosyStudio\data\cache\app.db"
db = sqlite3.connect(db_path)
cur = db.cursor()
cur.execute("DROP TABLE IF EXISTS webnovel_foreshadow")
db.commit()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='webnovel_foreshadow'")
left = cur.fetchall()
print("DROP 后残留:", left)
# 确认 open_loops 完好
cur.execute("SELECT COUNT(*) FROM webnovel_open_loops")
print("webnovel_open_loops 行数:", cur.fetchone()[0])
db.close()
assert not left, "表删除失败"
print("[OK] webnovel_foreshadow 已删除")
