# -*- coding: utf-8 -*-
"""细分：ctx 分析 prompt（#1191）内部构成 + 前文回顾块内部 + 一致性约束来源。"""
import sqlite3
import re

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()

# 1. ctx 分析 prompt 内部
r = cur.execute("SELECT user_prompt FROM llm_call_logs WHERE id=1191").fetchone()
up = r[0] or ""
print(f"== ctx_plot_gen 总 {len(up)} 字符 ==")
# 找资源目录/RAG候选/输出schema等小节
for marker in ["【资源目录】", "【RAG 候选】", "【RAG候选】", "RAG候选", "【前序步骤", "一致性维度", "输出格式", "structured_refs", "可选深度"]:
    idx = up.find(marker)
    if idx >= 0:
        # 估算该小节长度（到下一个双换行或 300 字）
        seg = up[idx:idx+400]
        print(f"  [{marker}] @{idx}: {seg[:120]!r}")

# 2. 前文回顾块（#1192）
r2 = cur.execute("SELECT user_prompt FROM llm_call_logs WHERE id=1192").fetchone()
up2 = r2[0] or ""
i = up2.find("【前文回顾】")
seg = up2[i:i+2900]
print(f"\n== 剧情生成 前文回顾块 {len(seg)} 字符 ==")
print(seg[:600])
print("  ...")
print(seg[-300:])

# 3. 草稿审查一致性约束（#1199）
r3 = cur.execute("SELECT user_prompt FROM llm_call_logs WHERE id=1199").fetchone()
up3 = r3[0] or ""
i3 = up3.find("【一致性约束】")
seg3 = up3[i3:i3+1700]
print(f"\n== 草稿审查 一致性约束块 {len(seg3)} 字符 ==")
print(seg3[:800])

db.close()
