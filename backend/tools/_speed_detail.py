# -*- coding: utf-8 -*-
"""明细：每次调用耗时/token/prompt长度，按时间排序。"""
import sqlite3
from datetime import datetime

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
print("== 表结构 ==")
for r in cur.execute("PRAGMA table_info(llm_call_logs)").fetchall():
    print(f"  {r[1]} {r[2]}")

print("\n== 17 条明细（按时间） ==")
rows = cur.execute("""
    SELECT id, created_at, prompt_name, model_name,
           latency_ms, input_tokens, output_tokens,
           LENGTH(system_prompt), LENGTH(user_prompt), LENGTH(raw_output),
           parse_success
    FROM llm_call_logs ORDER BY created_at
""").fetchall()
for r in rows:
    ts = datetime.fromtimestamp(r[1]).strftime("%m-%d %H:%M:%S") if r[1] else "-"
    print(f"#{r[0]:<4} {ts} {r[2]:<34} {r[3]:<22} "
          f"耗时{r[4]/1000:>5.1f}s 入{r[5]:>5} 出{r[6]:>5} "
          f"sys{r[7]:>6}字 user{r[8]:>7}字 出文{r[9]:>6}字 parse={r[10]}")

db.close()
