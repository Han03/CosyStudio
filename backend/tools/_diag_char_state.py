# -*- coding: utf-8 -*-
"""实测角色状态注入链路：
1. 数据库 character_state 分布
2. get_character_states_before_chapter(93,4) 返回
3. _fmt_character_states 渲染结果
4. 各步骤 _assemble_context 实际注入的 character_state 区块
"""
import asyncio, sys, os, sqlite3
sys.path.insert(0, r"C:\MyProjects\CosyStudio\backend")

from webnovel.repositories.character_state_repository import (
    get_character_states_before_chapter, get_character_states_by_chapter)

print("=== 1. 数据库分布 ===")
db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
cur = db.cursor()
rows = cur.execute(
    "SELECT chapter_number, COUNT(*) FROM webnovel_character_state WHERE project_id=93 "
    "GROUP BY chapter_number ORDER BY chapter_number").fetchall()
print(rows)
db.close()

print("\n=== 2. get_character_states_before_chapter(93, 4) ===")
states = get_character_states_before_chapter(93, 4)
print(f"返回 {len(states)} 条:", [s.get("character_name") for s in states])

print("\n=== 3. _fmt_character_states 渲染 ===")
from webnovel.pipeline.resource_registry import _fmt_character_states
if states:
    print(_fmt_character_states(states, depth="full")[:600])
else:
    print("（无数据可渲染）")


async def main():
    print("\n=== 4. 各步骤 assembled_context 中的 character_state 区块 ===")
    from webnovel.pipeline.context_analyzer import ContextAnalyzer, STEP_GOALS
    ca = ContextAnalyzer(999913, 4)
    env = {
        "project_id": 93,
        "script_id": 999913,
        "inventory": {
            "characters": [{"id": 221, "name": "林天昊", "type": "主角", "summary": "现代穿越者"},
                           {"id": 222, "name": "李威", "type": "护卫", "summary": "武艺高强"}],
            "foreshadows": [],
            "world_settings": [],
            "rag_candidates": [],
            "previous_chapters": [],
        },
        "structural_data": {"last_character_states": states},
    }
    # 模拟选择 character_state 的 selection
    from webnovel.pipeline.resource_registry import STEP_ASSEMBLY
    for step in STEP_ASSEMBLY:
        if "character_state" not in [s[0] for s in STEP_ASSEMBLY[step]["sections"]]:
            continue
        sel = {"structured_refs": [{"resource": "character_state", "depth": "full"}],
               "rag_queries": [], "custom_notes": []}
        try:
            step_ctx = await ca._assemble_context(step, sel, env)
            sec = step_ctx.get("sections", {}).get("character_state", "<无>")
            print(f"[{step:28}] 区块长度={len(sec)} | 首80字: {sec[:80]!r}")
        except Exception as e:
            print(f"[{step:28}] 注入失败: {type(e).__name__}: {e}")

asyncio.run(main())
