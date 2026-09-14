# -*- coding: utf-8 -*-
"""清理诊断/验证测试日志（__ 前缀）。"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
cur.execute("DELETE FROM llm_call_logs WHERE prompt_name LIKE '__%'")
print("deleted", cur.rowcount)
db.commit()
db.close()
