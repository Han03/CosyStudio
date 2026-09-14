# -*- coding: utf-8 -*-
"""补第3章应用后处理数据：角色状态 + 结尾钩子 + RAG 索引（基于库中现有成品）。

原因：第3章 apply 任务(186)跑在 fact_recorder 归口角色状态/钩子之前，导致
character_state 无第3章记录、chapter_meta 第3章 hook_content 为空，
第4章创作时 previous_hook / character_state 资源加载失败。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SCRIPT_ID = 999913
CHAPTER_INDEX = 3


async def main():
    from webnovel.services.webnovel_service import WebnovelService

    # 读第3章成品全文（内容存于 file_path 文件或台词库）
    from services.script_service import ScriptService
    svc = ScriptService()
    content = svc._read_script_chapter_content(SCRIPT_ID, CHAPTER_INDEX)
    if not content or not content.strip():
        print("第3章成品为空，无法补后处理")
        return
    print(f"第3章成品: {len(content)}字")

    svc = WebnovelService()
    context_inventory = svc._build_context_inventory_for_apply(SCRIPT_ID)
    print("context_inventory keys:", list(context_inventory.keys()))

    from webnovel.repositories import get_webnovel_project_by_script
    from webnovel.repositories.chapter_meta_repository import get_chapter_meta, update_chapter_meta
    from webnovel.repositories.character_state_repository import get_character_states_before_chapter
    from webnovel.pipeline.executors.fact_recorder_executor import FactRecorderExecutor

    project = get_webnovel_project_by_script(SCRIPT_ID)
    project_id = project["id"] if project else 0
    print(f"project_id={project_id}")

    # ── Phase 1: fact_recorder（事实/伏笔/爽点/钩子/角色状态） ──
    fact_executor = FactRecorderExecutor(SCRIPT_ID, CHAPTER_INDEX, task_id=0)
    result = await fact_executor.execute({
        "polished_content": content,
        "context_inventory": context_inventory,
    })
    print(f"fact_recorder: success={result.success} | {result.step_summary} | err={result.error_message}")

    # ── meta 标记已完成 ──
    meta = get_chapter_meta(project_id, CHAPTER_INDEX)
    if meta:
        update_chapter_meta(meta["id"], hook_type="已完成")
        print(f"meta: hook_type=已完成, hook_content={meta.get('hook_content', '')[:60]!r}")

    # ── Phase 2: RAG 索引 ──
    if project_id:
        await svc._store_rag_chunk(project_id, CHAPTER_INDEX, content)
        print("RAG 索引已构建")

    # ── 验证 ──
    states = get_character_states_before_chapter(project_id, CHAPTER_INDEX + 1)
    print(f"\n验证: 第{CHAPTER_INDEX}章角色状态 {len(states)} 条")
    for s in states:
        print(f"  - {s.get('character_name')}: {s.get('state_summary', '')[:40]}")
    meta2 = get_chapter_meta(project_id, CHAPTER_INDEX)
    print(f"验证: 第{CHAPTER_INDEX}章 hook_content={meta2.get('hook_content', '')[:80]!r}")


if __name__ == "__main__":
    asyncio.run(main())
