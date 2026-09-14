# -*- coding: utf-8 -*-
"""分析 #1280（润色）raw_output 的换行形态：字面\\n vs 真实换行"""
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()
row = cur.execute(
    "SELECT id, executor_name, prompt_name, raw_output, parsed_output, parse_success, output_tokens, length(raw_output) "
    "FROM llm_call_logs WHERE id=1280"
).fetchone()
db.close()
if not row:
    print("未找到 #1280")
    raise SystemExit

rid, ex, pn, raw, parsed, ok, otok, rawlen = row
print(f"id={rid} {ex} {pn} parse_success={ok} output_tokens={otok} raw_len={rawlen}")

# 1. 是否有字面反斜杠+n
print("\n--- raw_output 中字面 '\\\\n' 出现次数:", raw.count("\\n"))
print("--- raw_output 中真实换行符出现次数:", raw.count("\n"))
print("--- parsed_output 中字面 '\\\\n' 出现次数:", (parsed or "").count("\\n"))
print("--- parsed_output 中真实换行符出现次数:", (parsed or "").count("\n"))

# 2. raw_output 开头 300 字符的 repr（看真实形态）
print("\n--- raw_output 开头 repr ---")
print(repr(raw[:300]))

# 3. 如果 raw 是 JSON 字符串包装（含 \" 转义），检测首尾
print("\n--- raw 首字符/尾字符 ---")
print("first:", repr(raw[:1]), "last:", repr(raw[-1:]))

# 4. 中段采样
print("\n--- raw 中段 repr（第 400-600 字符）---")
print(repr(raw[400:600]))

# 5. parsed 开头 repr
print("\n--- parsed_output 开头 repr ---")
print(repr((parsed or "")[:300]))
