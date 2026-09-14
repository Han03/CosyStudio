# -*- coding: utf-8 -*-
"""生成类/审查类 prompt 渲染样本（只读）。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()


def show(name, n=1, head=900, tail=0):
    cur.execute(
        "SELECT id, user_prompt, raw_output, system_prompt FROM llm_call_logs "
        "WHERE prompt_name=? ORDER BY id DESC LIMIT ?", (name, n))
    for rid, up, raw, sp in cur.fetchall():
        print(f"\n{'='*70}\n[{name}] id={rid} user_prompt_len={len(up or '')} raw_len={len(raw or '')}")
        print(f"--- system_prompt ---\n{(sp or '')[:200]}")
        print(f"--- user_prompt 前{head}字 ---\n{(up or '')[:head]}")
        if tail:
            print(f"--- user_prompt 末{tail}字 ---\n{(up or '')[-tail:]}")
        print(f"--- raw 前300字 ---\n{(raw or '')[:300].replace(chr(10), '⏎')}")


show("draft_chapter_4", 1, 1100)
show("draft_polish", 1, 800, 500)
show("revise_draft", 1, 600, 400)
show("plan_chapter_plan", 2, 400, 0)
show("review_all_dimensions", 1, 700, 400)

db.close()
