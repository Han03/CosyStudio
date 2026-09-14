# -*- coding: utf-8 -*-
"""验证：world_settings 并入 fact_recorder 的提取与落库（dry-run：只落设定，不落其他块）。"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def main():
    from webnovel.pipeline.executors.fact_recorder_executor import FactRecorderExecutor
    from webnovel.repositories import get_worldview_by_project
    from core.model_executor import get_model_executor

    SCRIPT_ID, CHAPTER = 999913, 4
    PROJECT_ID = 93

    # 落库前世界观
    before = get_worldview_by_project(PROJECT_ID)
    before_summary = (before or {}).get("world_summary", "") or ""
    print(f"落库前 worldview 存在={bool(before)}，world_summary 长度={len(before_summary)}")

    content = open(os.path.join(os.path.dirname(__file__), "_e2e_polished.txt"),
                   encoding="utf-8").read()
    print(f"成品字数: {len(content)}")

    ex = FactRecorderExecutor(SCRIPT_ID, CHAPTER, 0)
    inventory = {
        "world_settings": [{"name": "明末"}],
        "characters": [{"name": n} for n in ["林天昊", "李威", "苏婉清", "林若兮", "重伤青年"]],
    }
    world_settings_text = ["明末"]
    characters_text = ["林天昊", "李威", "苏婉清", "林若兮", "重伤青年"]

    prompt_data = ex._load_prompt("fact_record")
    chapter_content = content[:4000]
    prompt = prompt_data["user_prompt"].format(
        chapter_content=chapter_content,
        world_settings=json.dumps(world_settings_text, ensure_ascii=False),
        characters=json.dumps(characters_text, ensure_ascii=False),
    )
    system_prompt = prompt_data["system_prompt"] or ""

    executor = get_model_executor()
    result = await executor.execute_text_chat(
        prompt=prompt,
        system_prompt=system_prompt,
        max_tokens=3000,
        script_id=SCRIPT_ID,
        project_id=PROJECT_ID,
        executor_name="fact_recorder",
        prompt_name="fact_record",
    )
    resp = result.get("content", "") if result else ""
    print(f"LLM 输出长度: {len(resp)}")

    # 解析（只关心 world_settings）
    (_, _, _, _, _, _, world_settings) = ex._parse_all(resp, SCRIPT_ID, PROJECT_ID)
    print(f"\n提取到 world_settings: {len(world_settings)} 条")
    for ws in world_settings:
        print(f"  - [{ws.get('category')}] {ws.get('name')}: {ws.get('content')[:60]}")

    # 只落库设定（dry-run 其他块）
    n = await ex._save_world_settings(PROJECT_ID, CHAPTER, world_settings)
    print(f"\n落库新增: {n} 条")

    after = get_worldview_by_project(PROJECT_ID)
    after_summary = (after or {}).get("world_summary", "") or ""
    print(f"落库后 world_summary 长度: {len(after_summary)}（+{len(after_summary) - len(before_summary)}）")
    if after_summary:
        print("\n--- world_summary 末尾 300 字 ---")
        print(after_summary[-300:])


if __name__ == "__main__":
    asyncio.run(main())
