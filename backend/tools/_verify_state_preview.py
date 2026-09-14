# -*- coding: utf-8 -*-
"""验证修复：资源目录中 character_state 候选显示 state_summary 内容"""
import asyncio, sys
sys.path.insert(0, r"C:\MyProjects\CosyStudio\backend")

from webnovel.repositories.character_state_repository import get_character_states_before_chapter
from webnovel.pipeline.context_analyzer import ContextAnalyzer

async def main():
    states = get_character_states_before_chapter(93, 4)
    ca = ContextAnalyzer(999913, 4)
    env = {
        "project_id": 93,
        "script_id": 999913,
        "inventory": {"characters": [], "foreshadows": [], "world_settings": [],
                      "power_system": None, "golden_finger": None, "character_group": None,
                      "previous_chapters": [], "rag_candidates": []},
        "structural_data": {"last_character_states": states},
    }
    text = ca._format_resource_candidates("character_state", env)
    print(text)
    assert all(("状态 " in line and len(line.split("状态 ")[-1]) > 0) or "位置" not in line
               for line in text.split("\n") if line.strip()), "仍有空状态"
    print("\n[OK] 资源目录角色状态预览已含 state_summary 内容")

asyncio.run(main())
