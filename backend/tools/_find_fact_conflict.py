# -*- coding: utf-8 -*-
"""列出最新批次 LLM 日志（task 205/206 重跑），定位倒数第4条"""
import sqlite3, datetime

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
start = datetime.datetime(2026, 9, 14, 15, 55, 0).timestamp()
rows = cur.execute(
    """SELECT id, executor_name, prompt_name, model_name, input_tokens, output_tokens,
       latency_ms, parse_success, success_strategy, substr(user_prompt,1,100)
       FROM llm_call_logs WHERE created_at >= ? ORDER BY id""",
    (start,),
).fetchall()
db.close()
print(f"批次数: {len(rows)}")
for i, r in enumerate(rows):
    marker = " <<< 倒数第4条" if i == len(rows) - 4 else ""
    print(
        f"[{i}] #{r[0]} {str(r[1])[:30]:30} {str(r[2])[:26]:26} in={r[3] and ''} "
        f"{r[6] / 1000:6.1f}s parse={r[7]} strat={str(r[8])[:22]:22}{marker}"
    )
    print(f"      user_prompt 开头: {r[9][:80]}")
