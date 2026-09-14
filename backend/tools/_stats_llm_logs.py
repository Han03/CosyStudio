# -*- coding: utf-8 -*-
"""LLM 日志库全面统计（只读）。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()

cur.execute("SELECT COUNT(*) FROM llm_call_logs")
total = cur.fetchone()[0]
print(f"总调用数: {total}")

print("\n== 按 prompt_name 统计 ==")
cur.execute(
    "SELECT prompt_name, COUNT(*) AS cnt, ROUND(AVG(input_tokens)) AS avg_in, "
    "ROUND(AVG(output_tokens)) AS avg_out, ROUND(AVG(latency_ms)/1000,1) AS avg_sec, "
    "SUM(CASE WHEN parse_success=1 THEN 1 ELSE 0 END) AS ok_parsed, "
    "MIN(created_at), MAX(created_at) "
    "FROM llm_call_logs GROUP BY prompt_name ORDER BY cnt DESC"
)
for r in cur.fetchall():
    name, cnt, avg_in, avg_out, avg_sec, ok, tmin, tmax = r
    rate = (ok / cnt * 100) if cnt else 0
    print(f"  {name:<42} n={cnt:<4} in={avg_in or 0:<6} out={avg_out or 0:<5} "
          f"{avg_sec or 0:>6}s parse_ok={rate:.0f}%")

print("\n== 模型分布 ==")
cur.execute("SELECT model_name, COUNT(*) FROM llm_call_logs GROUP BY model_name ORDER BY 2 DESC")
for r in cur.fetchall():
    print(" ", r)

print("\n== 最近20条调用（id/prompt/模型/in/out/ms/成功） ==")
cur.execute(
    "SELECT id, prompt_name, model_name, input_tokens, output_tokens, latency_ms, parse_success "
    "FROM llm_call_logs ORDER BY id DESC LIMIT 20"
)
for r in cur.fetchall():
    print(" ", r)

db.close()
