# -*- coding: utf-8 -*-
"""从 raw_output 提取 rag_queries 与 custom_notes，检查措辞是否受英文 step_name 影响"""
import sqlite3, re, json

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
ids = (1281, 1283, 1286, 1288, 1291)
rows = cur.execute(
    "SELECT id, prompt_name, raw_output FROM llm_call_logs "
    f"WHERE id IN ({','.join('?' * len(ids))})",
    ids,
).fetchall()
db.close()

def extract_queries(raw):
    """从模型输出 JSON 中提取 rag_queries 文本列表"""
    m = re.search(r'"rag_queries"\s*:\s*\[(.*?)\]\s*(?:,|\})', raw, re.S)
    if not m:
        return []
    seg = m.group(1)
    return re.findall(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"', seg)

for rid, pn, raw in rows:
    qs = extract_queries(raw)
    print(f"#{rid} {pn}")
    for q in qs:
        print(f"  - {q[:70]}")
    print()
