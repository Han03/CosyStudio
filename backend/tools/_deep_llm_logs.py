# -*- coding: utf-8 -*-
"""深挖审查类 parse 失败原因 + 关键 prompt 渲染样本（只读）。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()

print("== review_all_dimensions 最近3条 raw_output 形态 ==")
cur.execute(
    "SELECT id, raw_output, parsed_output, parse_success, success_strategy, strategies_tried, error_message "
    "FROM llm_call_logs WHERE prompt_name='review_all_dimensions' ORDER BY id DESC LIMIT 3"
)
for rid, raw, parsed, ok, strat, tried, err in cur.fetchall():
    print(f"\n--- id={rid} parse_success={ok} strategy={strat} tried={tried} err={err!r}")
    print("raw 前500字:", (raw or "")[:500].replace("\n", "⏎"))
    if parsed:
        print("parsed 前200字:", (parsed or "")[:200].replace("\n", "⏎"))

print("\n\n== ctx_analysis_chapter_plot_generator 最新 user_prompt 全貌 ==")
cur.execute(
    "SELECT id, user_prompt, raw_output FROM llm_call_logs "
    "WHERE prompt_name='ctx_analysis_chapter_plot_generator' ORDER BY id DESC LIMIT 1"
)
rid, up, raw = cur.fetchone()
print(f"id={rid} user_prompt 长度={len(up or '')}")
print("--- user_prompt ---")
print((up or "")[:2500])

print("\n\n== draft_chapter_4 最新 user_prompt 长度与结构 ==")
cur.execute(
    "SELECT id, user_prompt, raw_output FROM llm_call_logs WHERE prompt_name='draft_chapter_4' ORDER BY id DESC LIMIT 1"
)
r = cur.fetchone()
if r:
    rid, up, raw = r
    print(f"id={rid} user_prompt 长度={len(up or '')}")
    print("前1200字:", (up or "")[:1200].replace("\n", "⏎"))
    print("raw 前300字:", (raw or "")[:300].replace("\n", "⏎"))

db.close()
