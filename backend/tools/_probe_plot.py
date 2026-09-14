# -*- coding: utf-8 -*-
"""排查：剧情输出结构 + 修订调用点 word_cfg。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
r = cur.execute("SELECT raw_output FROM llm_call_logs WHERE id=1192").fetchone()
out = r[0] or ""
print(f"== chapter_plot #1192 输出前 400 字 ==\n{out[:400]}")
print(f"\n== 输出结构 ==\n  plots 数: {out.count('scene')}  description 数: {out.count('description')}")
db.close()
