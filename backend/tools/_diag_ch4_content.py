# -*- coding: utf-8 -*-
"""查 webnovel_chapter 第 4 章 content 形态 + #194 的 created_at 确认时间点"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
cur = db.cursor()
print("=== webnovel_chapter（第4章） ===")
try:
    rows = cur.execute(
        "SELECT id, chapter_index, project_id, length(content), content FROM webnovel_chapter "
        "WHERE chapter_index=4 ORDER BY id DESC LIMIT 3"
    ).fetchall()
    for r in rows:
        cid, ch, pid, clen, content = r
        if not content:
            print(f"#{cid} ch{ch} pid{pid}: content 空")
            continue
        literal_n = content.count("\\n")
        real_n = content.count("\n")
        print(f"#{cid} ch{ch} pid{pid}: len={clen} 字面\\n={literal_n} 真实换行={real_n} | {repr(content[:40])}")
except Exception as e:
    print("查询失败:", e)

print("\n=== #194 时间与来源 ===")
row = cur.execute(
    "SELECT id, chapter_index, task_type, created_at, updated_at FROM script_writing_tasks WHERE id=194"
).fetchone()
print(row)

print("\n=== 所有 ch4 任务（含非 completed） ===")
rows = cur.execute(
    "SELECT id, status, task_type, created_at FROM script_writing_tasks WHERE chapter_index=4 ORDER BY id"
).fetchall()
for r in rows:
    print(r)
db.close()
