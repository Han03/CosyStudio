# -*- coding: utf-8 -*-
"""T4 RAG 结果注入压缩：limit 5→3、每段 200→150 字。"""
p = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\resource_registry.py"
with open(p, encoding="utf-8") as f:
    t = f.read()

old = '''def _fmt_rag_results(rag_results, depth="full", limit=5):
    if not rag_results:
        return "（无检索结果）"
    parts = []
    for r in rag_results[:limit]:
        if isinstance(r, str):
            parts.append(r[:200])
        elif isinstance(r, dict):
            content = r.get("content", "")[:200]'''
new = '''def _fmt_rag_results(rag_results, depth="full", limit=3):
    if not rag_results:
        return "（无检索结果）"
    parts = []
    for r in rag_results[:limit]:
        if isinstance(r, str):
            parts.append(r[:150])
        elif isinstance(r, dict):
            content = r.get("content", "")[:150]'''
if old not in t:
    raise SystemExit("未找到")
t = t.replace(old, new, 1)
with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(t)
import py_compile
py_compile.compile(p, doraise=True)
print("[OK] RAG 结果 limit 5→3、每段 200→150 字")
