# -*- coding: utf-8 -*-
"""查 fact_record LLM 日志。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
cur.execute(
    "SELECT id, raw_output, parsed_output, parse_success, error_message "
    "FROM llm_call_logs WHERE prompt_name='fact_record' ORDER BY id DESC LIMIT 3"
)
for rid, raw, parsed, ok, err in cur.fetchall():
    print("=== id", rid, "parse_success", ok, "err", repr(err))
    print("raw[:400]:", (raw or "")[:400].replace("\n", " "))
    print("parsed[:400]:", (parsed or "")[:400].replace("\n", " "))
    print()
db.close()
