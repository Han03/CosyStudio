# -*- coding: utf-8 -*-
"""验证：纯文本节点 parse 语义修复 + T2 ctx 输入瘦身效果。"""
import sqlite3
import datetime

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()

def ts(ca):
    return datetime.datetime.fromtimestamp(ca).strftime("%H:%M:%S") if ca else "?"

rows = cur.execute(
    "SELECT id, prompt_name, model_name, input_tokens, output_tokens, latency_ms, "
    "strategies_tried, success_strategy, parse_success, length(raw_output), length(parsed_output), created_at "
    "FROM llm_call_logs ORDER BY id DESC LIMIT 12"
).fetchall()

print("== 最新批次（修复后）==")
tot_in = 0
for r in reversed(rows):
    rid, pn, model, it, ot, lat, st, ss, ps, rlen, plen, ca = r
    tot_in += it or 0
    tag = ""
    if pn in ("draft_chapter_4", "revise_draft", "draft_polish"):
        tag = "  <<纯文本节点"
    print(f"#{rid} {ts(ca)} {pn:<28} 入{it:>5} 出{ot:>5} {(lat or 0)/1000:>5.1f}s "
          f"strat={st} succ={ss!r:<16} parse={ps} raw={rlen} parsed={plen}{tag}")
print(f"合计入 {tot_in} tok")

# 基线对比
base_in = 32728  # T1 实测
print(f"\nT1(前文瘦身后) 入 {base_in} -> 本轮入 {tot_in} 变化 {(tot_in-base_in)/base_in*100:+.0f}%")
base_t0 = 35832
print(f"T0(基线) 入 {base_t0} -> 本轮入 {tot_in} 变化 {(tot_in-base_t0)/base_t0*100:+.0f}%")
db.close()
