# -*- coding: utf-8 -*-
"""按时间看 token 差异是否与代码版本相关。"""
import sqlite3
import datetime

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
cur.execute("""
    SELECT id, prompt_name, model_name, input_tokens, output_tokens, latency_ms, created_at
    FROM llm_call_logs
    WHERE prompt_name LIKE 'ctx_analysis%' OR prompt_name IN ('review_all_dimensions','init_worldview','fact_record')
    ORDER BY id
""")
for r in cur.fetchall():
    ts = datetime.datetime.fromtimestamp(r[6]).strftime("%m-%d %H:%M:%S") if r[6] else "?"
    print(f"id={r[0]:<5} tok={r[3]}/{r[4]:<5} lat={r[5]:<7} {ts}  {r[1]}")
db.close()
