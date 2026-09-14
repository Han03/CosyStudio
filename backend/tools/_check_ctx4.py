# -*- coding: utf-8 -*-
"""核对第4章 ctx_analysis 日志（只读）。"""
import json
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
cur.execute(
    "SELECT id, prompt_name, raw_output, created_at FROM llm_call_logs "
    "WHERE prompt_name LIKE 'ctx_analysis%' ORDER BY id DESC LIMIT 6"
)
for rid, pname, raw, ts in cur.fetchall():
    print("===", rid, pname, "ts=", ts)
    try:
        s = raw.find("{")
        e = raw.rfind("}")
        d = json.loads(raw[s:e + 1])
        refs = d.get("structured_refs", [])
        print("  refs:", len(refs), [r.get("resource") for r in refs])
    except Exception as ex:
        print("  parse fail:", ex)
db.close()
