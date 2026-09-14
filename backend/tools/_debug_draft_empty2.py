# -*- coding: utf-8 -*-
"""查 draft_chapter 全部记录 + 空输出重试情况。"""
import sqlite3
import datetime

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()

def ts(ca):
    return datetime.datetime.fromtimestamp(ca).strftime("%m-%d %H:%M:%S") if ca else "?"

rows = cur.execute(
    "SELECT id, request_id, prompt_name, model_name, length(raw_output), "
    "parse_success, error_message, input_tokens, output_tokens, latency_ms, created_at "
    "FROM llm_call_logs WHERE prompt_name LIKE '%draft%' OR prompt_name LIKE '%chapter%' "
    "ORDER BY id DESC LIMIT 40"
).fetchall()
print("== draft/草稿相关记录（最近 40 条）==")
for r in rows:
    rid, req, pn, model, rlen, ps, err, it, ot, lat, ca = r
    print(f"#{rid} {ts(ca)} {pn:<28} {model:<22} raw_len={rlen or 0} parse={ps} "
          f"入{it} 出{ot} lat={(lat or 0)/1000:.0f}s err={str(err or '')[:50]!r}")

# 空输出记录（raw_output 为空的全部）
print("\n== raw_output 为空或极短的记录（最近 30 天）==")
rows2 = cur.execute(
    "SELECT id, request_id, prompt_name, model_name, parse_success, error_message, "
    "strategies_tried, success_strategy, latency_ms, created_at "
    "FROM llm_call_logs WHERE (raw_output IS NULL OR length(raw_output) < 10) "
    "ORDER BY id DESC LIMIT 20"
).fetchall()
for r in rows2:
    rid, req, pn, model, ps, err, st, ss, lat, ca = r
    print(f"#{rid} {ts(ca)} {pn:<28} {model:<22} parse={ps} lat={(lat or 0)/1000:.0f}s "
          f"strategies={st!r} success={ss!r} err={str(err or '')[:60]!r}")

db.close()
