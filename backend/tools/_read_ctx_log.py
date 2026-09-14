# -*- coding: utf-8 -*-
"""核对 app_llm_logs.db 中 ctx_analysis_* 日志是否符合新 schema。"""
import json
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("tables:", [r[0] for r in cur.fetchall()])

cur.execute("PRAGMA table_info(llm_call_logs)")
cols = [c[1] for c in cur.fetchall()]
print("cols:", cols)

cur.execute(
    "SELECT id, prompt_name, user_prompt, raw_output, created_at FROM llm_call_logs "
    "WHERE prompt_name LIKE 'ctx_analysis_%' ORDER BY id DESC LIMIT 8"
)
rows = cur.fetchall()
print(f"\nctx_analysis 日志 {len(rows)} 条（最近）")

for rid, pname, prompt, response, ts in rows:
    print(f"\n=== id={rid} {pname} ts={ts} ===")
    # 检查 prompt 是否含三段式引导
    keys = ["structured_refs", "rag_queries", "custom_notes", "资源目录", "选择约束"]
    print("prompt 含关键标记:", {k: (k in (prompt or "")) for k in keys})
    # 尝试解析 response 中的 JSON
    resp = response or ""
    # 提取 { 开始到结尾的 JSON
    try:
        start = resp.find("{")
        end = resp.rfind("}")
        data = json.loads(resp[start:end + 1])
        print("response JSON keys:", list(data.keys()))
        refs = data.get("structured_refs", [])
        print("structured_refs 数量:", len(refs))
        for r in refs[:10]:
            print("   ref:", json.dumps(r, ensure_ascii=False)[:150])
        print("rag_queries 数量:", len(data.get("rag_queries", [])))
        print("custom_notes 数量:", len(data.get("custom_notes", [])))
    except Exception as e:
        print("response 解析失败:", e)
        print("response 前300字:", resp[:300])

db.close()
