# -*- coding: utf-8 -*-
"""对比有/无 token 记录的具体字段。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
print("=== 有 token 的（init/review） ===")
cur.execute("""
    SELECT id, prompt_name, executor_name, model_name, input_tokens, output_tokens, latency_ms
    FROM llm_call_logs WHERE input_tokens>0 ORDER BY id LIMIT 6
""")
for r in cur.fetchall():
    print(r)
print()
print("=== 无 token 的（ctx_analysis/draft） ===")
cur.execute("""
    SELECT id, prompt_name, executor_name, model_name, input_tokens, output_tokens, latency_ms
    FROM llm_call_logs WHERE input_tokens=0 AND output_tokens=0 AND raw_output != '' ORDER BY id DESC LIMIT 8
""")
for r in cur.fetchall():
    print(r)
db.close()
