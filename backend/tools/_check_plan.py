# -*- coding: utf-8 -*-
"""查 plan_chapter_plan 解析失败样本。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
cur.execute(
    "SELECT id, prompt_name, parse_success, error_message, substr(raw_output,1,300) "
    "FROM llm_call_logs WHERE prompt_name='plan_chapter_plan' ORDER BY id"
)
for r in cur.fetchall():
    print(r[0], "| ok=", r[2], "| err=", (r[3] or "")[:60])
    print("   raw:", (r[4] or "").replace("\n", "⏎"))
db.close()
