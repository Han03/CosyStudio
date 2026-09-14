# -*- coding: utf-8 -*-
"""排查第4章创作前置数据：规划/前章成品/meta hook（只读）。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
cur = db.cursor()

print("== script_chapters（成品入库） ==")
cur.execute("SELECT id, script_id, chapter_index, title, word_count FROM script_chapters ORDER BY chapter_index")
for r in cur.fetchall():
    print(r)

print("\n== script_chapter_versions（最近成品版本） ==")
cur.execute("SELECT id, script_id, chapter_index, word_count, created_at FROM script_chapter_versions ORDER BY chapter_index")
for r in cur.fetchall():
    print(r)

print("\n== webnovel_chapter_plan（1-6章） ==")
cur.execute("SELECT id, chapter_index, chapter_title, summary FROM webnovel_chapter_plan ORDER BY chapter_index LIMIT 6")
for r in cur.fetchall():
    print(r[:4])

print("\n== webnovel_chapter_meta（1-6章 hook 字段） ==")
cur.execute("SELECT id, chapter_number, hook_content, ending_emotion, ending_location FROM webnovel_chapter_meta ORDER BY chapter_number LIMIT 6")
for r in cur.fetchall():
    print(r)

print("\n== webnovel_chapter_meta 50行分布 ==")
cur.execute("SELECT MIN(chapter_number), MAX(chapter_number), COUNT(*) FROM webnovel_chapter_meta")
print(cur.fetchone())

print("\n== webnovel_chapter_plot（1-4章缓存） ==")
cur.execute("SELECT id, project_id, chapter_index, COUNT(*) FROM webnovel_chapter_plot GROUP BY chapter_index ORDER BY chapter_index")
for r in cur.fetchall():
    print(r)

print("\n== webnovel_character_state（1-4章记录数） ==")
cur.execute("SELECT chapter_index, COUNT(*) FROM webnovel_character_state GROUP BY chapter_index ORDER BY chapter_index")
for r in cur.fetchall():
    print(r)

db.close()
