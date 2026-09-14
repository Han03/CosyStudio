# -*- coding: utf-8 -*-
"""查 script_chapter_versions 第4章 content 形态（apply 后正文）"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
cur = db.cursor()
rows = cur.execute(
    "SELECT id, script_id, chapter_index, length(content), content, word_count, created_at "
    "FROM script_chapter_versions WHERE chapter_index=4 ORDER BY id DESC LIMIT 5"
).fetchall()
print(f"第4章版本数: {len(rows)}")
for r in rows:
    vid, sid, ch, clen, content, wc, created = r
    if not content:
        print(f"#{vid} script{sid} ch{ch} wc={wc}: content 空")
        continue
    literal_n = content.count("\\n")
    real_n = content.count("\n")
    print(
        f"#{vid} script{sid} ch{ch} wc={wc} len={clen} 字面\\n={literal_n} 真实换行={real_n} | {repr(content[:40])}"
    )
db.close()
