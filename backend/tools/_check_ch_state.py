# -*- coding: utf-8 -*-
"""查剧本章节状态：规划/成品/剧情缓存/角色状态。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
cur = db.cursor()

print("== webnovel_chapter_plan (剧本999913) ==")
cur.execute("SELECT chapter_index, chapter_title FROM webnovel_chapter_plan WHERE script_id=999913 ORDER BY chapter_index")
for r in cur.fetchall():
    print(" ", r)

print("\n== script_chapters ==")
cur.execute("SELECT id, script_id, chapter_index, title, word_count FROM script_chapters WHERE script_id=999913 ORDER BY chapter_index")
for r in cur.fetchall():
    print(" ", r)

print("\n== webnovel_chapter_plot 缓存 ==")
cur.execute("SELECT chapter_index, COUNT(*), GROUP_CONCAT(DISTINCT plot_type) FROM webnovel_chapter_plot WHERE project_id=93 GROUP BY chapter_index ORDER BY chapter_index")
for r in cur.fetchall():
    print(" ", r)

print("\n== webnovel_chapter_meta (hook) ==")
cur.execute("SELECT chapter_index, hook_content FROM webnovel_chapter_meta WHERE project_id=93 ORDER BY chapter_index")
for r in cur.fetchall():
    print(" ", r[0], "|", (r[1] or "")[:40])

print("\n== character_state 最新章 ==")
cur.execute("SELECT chapter_number, character_name, substr(state_summary,1,30) FROM webnovel_character_state WHERE project_id=93 ORDER BY chapter_number, id")
for r in cur.fetchall():
    print(" ", r)

db.close()
