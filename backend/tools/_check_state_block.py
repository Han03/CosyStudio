# -*- coding: utf-8 -*-
"""查最新批次 ctx 日志 user_prompt 中的【上章末角色状态】区块是否存在/为空"""
import sqlite3, re

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
ids = (1281, 1283, 1286, 1288, 1291)
rows = cur.execute(
    "SELECT id, prompt_name, user_prompt FROM llm_call_logs "
    f"WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
db.close()

for rid, pn, up in rows:
    # 找【上章末角色状态】区块
    m = re.search(r"【上章末角色状态】\n(.*?)(?=\n\s*【|\Z)", up, re.S)
    if m:
        block = m.group(1).strip()
        print(f"#{rid} {pn}: 区块存在，长度={len(block)}")
        print("   ", block[:120].replace("\n", " | "))
    else:
        # 检查其他角色相关区块
        for key in ["角色状态", "角色卡", "角色清单"]:
            if key in up:
                print(f"#{rid} {pn}: 无【上章末角色状态】，但含『{key}』")
                break
        else:
            print(f"#{rid} {pn}: 无【上章末角色状态】区块")
    print()
