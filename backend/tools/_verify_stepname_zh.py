# -*- coding: utf-8 -*-
"""验证 ctx 分析 prompt 渲染：步骤名显示为中文"""
import asyncio, sys, os
sys.path.insert(0, r"C:\MyProjects\CosyStudio\backend")

from webnovel.pipeline.context_analyzer import ContextAnalyzer, STEP_GOALS

async def main():
    ca = ContextAnalyzer(999913, 4)
    env = {
        "project_id": 93,
        "script_id": 999913,
        "inventory": {
            "characters": [],
            "foreshadows": [],
            "world_settings": [],
            "rag_candidates": [],
            "previous_chapters": [],
        },
        "structural_data": {},
    }
    for step in ["chapter_plot_generator", "draft_generator", "draft_reviewer", "draft_polisher", "chapter_plot_reviewer"]:
        goal = STEP_GOALS[step]
        prompt = ca._build_analysis_prompt(step, goal, env, None)
        first_line = prompt.split("\n")[0].strip()
        print(f"{step:28} -> {first_line[:70]}")

asyncio.run(main())
