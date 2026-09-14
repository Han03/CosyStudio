# -*- coding: utf-8 -*-
"""查 strategies_tried 相关记录：表结构 + 含 '12' 或值较大的记录。"""
import sqlite3
import datetime

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()

# 表结构
cols = cur.execute("PRAGMA table_info(llm_call_logs)").fetchall()
print("== 表结构 ==")
for c in cols:
    print(f"  {c[1]} ({c[2]})")

# 找 strategies_tried 含 12 的记录
print("\n== strategies_tried 含 '12' 的记录 ==")
rows = cur.execute(
    "SELECT id, request_id, prompt_name, model_name, strategies_tried, success_strategy, "
    "parse_success, substr(raw_output,1,60), length(raw_output), error_message, created_at "
    "FROM llm_call_logs WHERE strategies_tried LIKE '%12%' ORDER BY id DESC LIMIT 15"
).fetchall()
def ts(ca):
    return datetime.datetime.fromtimestamp(ca).strftime("%m-%d %H:%M:%S") if ca else "?"
for r in rows:
    rid, req, pn, model, st, ss, ps, raw, rlen, err, ca = r
    print(f"#{rid} {ts(ca)} {pn:<26} model={model} parse={ps} raw_len={rlen}")
    print(f"    strategies_tried={st!r}")
    print(f"    success_strategy={ss!r}")
    print(f"    raw={raw!r}")
    print(f"    err={str(err or '')[:80]!r}")

# 最近 5 条记录完整字段
print("\n== 最近 5 条记录的关键字段 ==")
rows2 = cur.execute(
    "SELECT id, prompt_name, strategies_tried, success_strategy, parse_success, "
    "length(raw_output), length(parsed_output), error_message, created_at "
    "FROM llm_call_logs ORDER BY id DESC LIMIT 5"
).fetchall()
for r in rows2:
    print(f"#{r[0]} {r[1]} strategies={r[2]!r} success={r[3]!r} parse={r[4]} "
          f"raw_len={r[5]} parsed_len={r[6]} err={str(r[7] or '')[:60]!r}")

db.close()
