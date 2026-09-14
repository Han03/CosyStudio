# -*- coding: utf-8 -*-
"""排查草稿生成异常：最新 draft_chapter 调用记录（输出空、多次尝试）。"""
import sqlite3
import datetime

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()

def ts(ca):
    return datetime.datetime.fromtimestamp(ca).strftime("%m-%d %H:%M:%S") if ca else "?"

# 最近 30 条记录，找 draft_chapter / 草稿相关
rows = cur.execute(
    "SELECT id, request_id, executor_name, prompt_name, model_name, "
    "substr(raw_output,1,80), parsed_output, parse_success, error_message, "
    "input_tokens, output_tokens, latency_ms, created_at "
    "FROM llm_call_logs ORDER BY id DESC LIMIT 30"
).fetchall()

print("== 最近 30 条调用 ==")
for r in rows:
    rid, req, ex, pn, model, raw, parsed, ps, err, it, ot, lat, ca = r
    raw_s = (raw or "")[:50].replace("\n", "\\n")
    err_s = (err or "")[:60]
    print(f"#{rid} {ts(ca)} {pn:<26} {model:<22} 入{it} 出{ot} "
          f"parse={ps} lat={(lat or 0)/1000:.0f}s raw={raw_s!r} err={err_s!r}")

db.close()
