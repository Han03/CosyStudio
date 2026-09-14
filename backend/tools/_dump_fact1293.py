# -*- coding: utf-8 -*-
"""提取 #1293 fact_record 完整 prompt / raw_output / parsed_output"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
row = cur.execute(
    "SELECT id, system_prompt, user_prompt, raw_output, parsed_output, success_strategy "
    "FROM llm_call_logs WHERE id=1293"
).fetchone()
db.close()
if not row:
    print("未找到 #1293")
    raise SystemExit

rid, sp, up, raw, parsed, strat = row
print(f"===== #1293 system_prompt =====\n{sp}\n")
print(f"===== #1293 user_prompt（全文）=====\n{up}\n")
print(f"===== raw_output（前 2500 字符）=====\n{raw[:2500]}\n")
print(f"===== parsed_output =====\n{parsed[:2500]}")
