# -*- coding: utf-8 -*-
"""查 token 记录差异：按 prompt_name 统计有/无 token。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
cur.execute("""
    SELECT prompt_name, COUNT(*) AS n,
           SUM(CASE WHEN input_tokens>0 OR output_tokens>0 THEN 1 ELSE 0 END) AS with_tok,
           SUM(CASE WHEN input_tokens=0 AND output_tokens=0 THEN 1 ELSE 0 END) AS no_tok,
           GROUP_CONCAT(DISTINCT model_name) AS models
    FROM llm_call_logs GROUP BY prompt_name ORDER BY n DESC
""")
print(f"{'prompt_name':<42}{'n':>4}{'with_tok':>9}{'no_tok':>8}  models")
for r in cur.fetchall():
    print(f"{r[0]:<42}{r[1]:>4}{r[2]:>9}{r[3]:>8}  {r[4]}")
db.close()
