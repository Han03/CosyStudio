# -*- coding: utf-8 -*-
"""T1 实测对比：拉最新批次 12 次调用明细（输入token/耗时），与 T0 基线对比。"""
import sqlite3
import datetime

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
rows = cur.execute(
    "SELECT id, prompt_name, model_name, input_tokens, output_tokens, latency_ms, created_at "
    "FROM llm_call_logs ORDER BY id DESC LIMIT 12"
).fetchall()

def ts(created):
    return datetime.datetime.fromtimestamp(created).strftime("%H:%M:%S")

print("== T1 实测批次（最新 12 条）==")
tot_in = tot_out = 0
for r in reversed(rows):
    rid, pn, model, it, ot, lat, ca = r
    tot_in += it or 0; tot_out += ot or 0
    print(f"  #{rid} {ts(ca)} {pn:<28} {model:<22} 入{it:>5} 出{ot:>5} {(lat or 0)/1000:>5.1f}s")
print(f"  合计: 入 {tot_in} tok, 出 {tot_out} tok")

# 基线（T0，#1191-#1202）
base = [(1191,3593),(1192,4561),(1193,3060),(1194,2680),(1195,710),(1196,3445),
        (1197,2316),(1198,3336),(1199,3005),(1200,2825),(1201,2816),(1202,3485)]
b_in = sum(x[1] for x in base)
print(f"\n基线(T0) 入 {b_in} tok -> T1 入 {tot_in} tok  变化 {(tot_in-b_in)/b_in*100:+.0f}%")
print(f"基线(T0) 出 {sum([4323,329,2015,1963,523,2538,3402,431,298,382,268,205])} tok -> T1 出 {tot_out} tok")
db.close()
