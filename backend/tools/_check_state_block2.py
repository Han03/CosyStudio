# -*- coding: utf-8 -*-
"""查执行器日志 user_prompt 中的【上章末角色状态】区块（真正注入点）"""
import sqlite3, re

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
ids = (1282, 1284, 1285, 1287, 1289, 1290, 1292)
rows = cur.execute(
    "SELECT id, executor_name, prompt_name, user_prompt FROM llm_call_logs "
    f"WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
db.close()

for rid, ex, pn, up in rows:
    m = re.search(r"【上章末角色状态】\n(.*?)(?=\n\s*【|\Z)", up, re.S)
    if m:
        block = m.group(1).strip()
        print(f"#{rid} {ex} {pn}: 区块存在，长度={len(block)}")
        print("   ", block[:150].replace("\n", " | "))
    else:
        print(f"#{rid} {ex} {pn}: 【无】上章末角色状态区块")
    print()
