# -*- coding: utf-8 -*-
"""查 ctx_analysis 日志：prompt 中 step_name 呈现 + 分析输出（RAG查询/选择）质量"""
import sqlite3, json

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
ids = (1281, 1283, 1286, 1288, 1291)
rows = cur.execute(
    "SELECT id, prompt_name, user_prompt, parsed_output, raw_output "
    f"FROM llm_call_logs WHERE id IN ({','.join('?'*len(ids))})",
    ids,
).fetchall()
db.close()

for rid, pn, up, parsed, raw in rows:
    print(f"===== #{rid} {pn} =====")
    # prompt 首段（步骤名呈现）
    head = up[:120].replace("\n", " ")
    print("prompt 首段:", head)
    # 解析输出
    try:
        p = json.loads(parsed) if isinstance(parsed, str) and parsed.startswith("{") else parsed
    except Exception:
        p = None
    if isinstance(p, dict):
        qs = p.get("rag_queries") or []
        refs = p.get("structured_refs") or []
        print(f"  rag_queries ({len(qs)}):")
        for q in qs:
            print(f"    - {q.get('text','')}  types={q.get('types')}")
        print(f"  structured_refs ({len(refs)}):")
        for r in refs:
            print(f"    - {r.get('resource')} ids={r.get('ids') or r.get('previous_chapter')}")
    else:
        print("  parsed 非 dict:", str(parsed)[:200])
    print()
