# -*- coding: utf-8 -*-
"""排查：角色状态表结构、第3章应用结果相关数据（只读）。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
cur = db.cursor()

print("== webnovel_character_state 表结构 ==")
cur.execute("PRAGMA table_info(webnovel_character_state)")
for r in cur.fetchall():
    print(r[1], r[2])

print("\n== webnovel_character_state 最近记录（前5） ==")
cur.execute("SELECT * FROM webnovel_character_state ORDER BY id DESC LIMIT 5")
cols = [d[0] for d in cur.description]
for r in cur.fetchall():
    print(dict(zip(cols, r)))

print("\n== webnovel_fact 相关表 ==")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE '%fact%' OR name LIKE '%item%' OR name LIKE '%relation%')")
for r in cur.fetchall():
    print(r[0])

print("\n== 最近写入的 writing task（3-4章） ==")
cur.execute("SELECT id, chapter_index, task_type, status, progress, created_at, updated_at FROM script_writing_tasks WHERE chapter_index IN (3,4) ORDER BY id DESC LIMIT 6")
for r in cur.fetchall():
    print(r)

db.close()
