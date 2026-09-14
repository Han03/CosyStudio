# -*- coding: utf-8 -*-
"""LLM 日志速度瓶颈分析：按 prompt_name 聚合耗时/token/调用次数。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()

# 总览
total = cur.execute("SELECT COUNT(*), SUM(latency_ms), AVG(latency_ms) FROM llm_call_logs").fetchone()
print(f"总调用 {total[0]} 次，总耗时 {total[1]/1000:.1f}s，平均 {total[2]/1000:.2f}s\n")

# 按 prompt_name 聚合
rows = cur.execute("""
    SELECT prompt_name,
           COUNT(*) AS n,
           ROUND(AVG(latency_ms)) AS avg_ms,
           ROUND(MAX(latency_ms)) AS max_ms,
           ROUND(AVG(input_tokens)) AS avg_in,
           ROUND(AVG(output_tokens)) AS avg_out,
           ROUND(AVG(input_tokens+output_tokens)) AS avg_tok,
           ROUND(SUM(latency_ms)/1000) AS total_s,
           ROUND(100.0*SUM(latency_ms)/(SELECT SUM(latency_ms) FROM llm_call_logs),1) AS pct
    FROM llm_call_logs
    GROUP BY prompt_name
    ORDER BY total_s DESC
""").fetchall()

print(f"{'prompt_name':<38}{'次数':>4}{'平均s':>7}{'最大s':>7}{'入tok':>7}{'出tok':>7}{'总tok':>7}{'总s':>7}{'占比':>6}")
for r in rows:
    print(f"{r[0]:<38}{r[1]:>4}{r[2]/1000:>7.1f}{r[3]/1000:>7.1f}{r[4]:>7}{r[5]:>7}{r[6]:>7}{r[7]:>7}{r[8]:>5.1f}%")

# 模型分布
print("\n== 模型分布 ==")
for r in cur.execute("SELECT model_name, COUNT(*), ROUND(AVG(latency_ms)/1000,2) FROM llm_call_logs GROUP BY model_name ORDER BY 2 DESC").fetchall():
    print(f"  {r[0]}: {r[1]} 次，平均 {r[2]}s")

db.close()
