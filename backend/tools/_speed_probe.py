# -*- coding: utf-8 -*-
"""抽查高 tok/字 比值调用的 raw_output 结构。"""
import sqlite3
import re

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()

for pid in (1182, 1177, 1180, 1172):
    r = cur.execute(
        "SELECT prompt_name, output_tokens, raw_output FROM llm_call_logs WHERE id=?", (pid,)).fetchone()
    name, tok, out = r[0], r[1], r[2] or ""
    print(f"=== {name} (id={pid}) out_tok={tok} 输出字符={len(out)} ===")
    print(f"  前 260 字: {out[:260].replace(chr(10), '⏎')}")
    # 统计非正文噪音：JSON 标记、markdown、空行
    braces = out.count("{") + out.count("}")
    md = out.count("**") + out.count("##") + out.count("```")
    newlines = out.count("\n")
    print(f"  花括号={braces} markdown标记={md} 换行={newlines}")
    print()
db.close()
