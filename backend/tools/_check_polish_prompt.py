# -*- coding: utf-8 -*-
"""查本次运行润色 prompt 的字数指令与字数配置。"""
import sqlite3
import re

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
cur.execute(
    "SELECT id, user_prompt, model_name, input_tokens, output_tokens, parse_success, created_at "
    "FROM llm_call_logs WHERE prompt_name='draft_polish' ORDER BY id DESC LIMIT 1")
r = cur.fetchone()
print("id=", r[0], "model=", r[2], "tok=", r[3], "/", r[4], "parse=", r[5])
up = r[1] or ""
for kw in ["字数", "扩写", "3200", "4800", "800", "1200", "下限", "上限", "word_min", "word_max", "polish"]:
    for m in re.finditer(kw, up):
        s = max(0, m.start() - 30)
        print(f"  [{kw}] ...{up[s:m.start() + 40].replace(chr(10), ' ')}...")
        break
print("\n--- 前 500 字 ---")
print(up[:500])
db.close()
