# -*- coding: utf-8 -*-
"""实测各调用 user_prompt 构成：按【区块标题】分块统计字符。"""
import sqlite3
import re

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()

targets = [
    (1192, "剧情生成"),
    (1197, "草稿"),
    (1202, "润色"),
    (1194, "剧情审查"),
    (1199, "草稿审查"),
    (1195, "剧情修订"),
    (1200, "草稿修订"),
    (1191, "ctx_plot_gen"),
]

for pid, name in targets:
    r = cur.execute("SELECT user_prompt FROM llm_call_logs WHERE id=?", (pid,)).fetchone()
    up = r[0] or ""
    # 按【...】标题切块
    blocks = re.split(r"\n(?=【)", up)
    print(f"\n=== {name} (#{pid}) 总 {len(up)} 字符 ===")
    total_other = 0
    for b in blocks:
        title = b.split("】", 1)[0] + "】" if "】" in b else b[:20]
        body = b.split("】", 1)[1] if "】" in b else b
        body_len = len(body)
        if body_len > 100:
            print(f"  {title:<24} {body_len:>6} 字符")
        else:
            total_other += len(b)
    if total_other:
        print(f"  {'（其他小段合计）':<22} {total_other:>6} 字符")

db.close()
