# -*- coding: utf-8 -*-
"""修复后验证：#194 polished 形态 + 前后端链路确认"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
cur = db.cursor()
row = cur.execute(
    "SELECT id, polished FROM script_writing_tasks WHERE id=194"
).fetchone()
db.close()
rid, polished = row
print(f"#{rid}: len={len(polished)} 字面\\n={polished.count(chr(92)+'n')} 真实换行={polished.count(chr(10))}")
print("开头:", repr(polished[:80]))
