# -*- coding: utf-8 -*-
"""查 #1288 user_prompt 中含'状态'的行 + 角色状态相关区块"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
row = cur.execute(
    "SELECT user_prompt FROM llm_call_logs WHERE id=1288"
).fetchone()
db.close()
up = row[0]

print("=== 含『状态』的行 ===")
for i, line in enumerate(up.split("\n")):
    if "状态" in line:
        print(f"  {line}")
print("\n=== 含『角色』的行（前 25 条）===")
n = 0
for line in up.split("\n"):
    if "角色" in line:
        print(f"  {line[:100]}")
        n += 1
        if n >= 25:
            break
