# -*- coding: utf-8 -*-
"""最新批次 LLM 日志明细（e2e task 204，15:36 之后）"""
import sqlite3, datetime

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
start = datetime.datetime(2026, 9, 14, 15, 36, 30).timestamp()
rows = cur.execute(
    """SELECT id, executor_name, prompt_name, model_name, input_tokens, output_tokens,
       latency_ms, length(user_prompt), length(raw_output)
       FROM llm_call_logs WHERE created_at >= ? ORDER BY id""",
    (start,),
).fetchall()
print(f"批次数: {len(rows)}")
tot_in = tot_out = tot_ms = 0
for r in rows:
    tot_in += r[4] or 0
    tot_out += r[5] or 0
    tot_ms += r[6] or 0
    print(
        f"#{r[0]} {str(r[1])[:28]:28} {str(r[2])[:26]:26} {str(r[3])[:20]:20} "
        f"in={r[4]} out={r[5]} {r[6] / 1000:6.1f}s user_len={r[7]} out_len={r[8]}"
    )
print(f"--- 合计: {tot_in} tok in, {tot_out} tok out, {tot_ms / 1000:.1f}s")
db.close()
