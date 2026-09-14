# -*- coding: utf-8 -*-
"""第4章 apply 落库：成品写回源任务 → 执行 apply 工作流（保存章节+事实提取+RAG）→ 验证。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SCRIPT_ID = 999913
CHAPTER_INDEX = 4
SOURCE_TASK_ID = 194  # _e2e_run.py 创建的 write 任务


async def main():
    # ── 1. 成品写回源任务 ──
    polished_path = os.path.join(os.path.dirname(__file__), "_e2e_polished.txt")
    with open(polished_path, encoding="utf-8") as f:
        content = f.read()
    if not content.strip():
        print("成品为空，中止")
        return
    print(f"成品字数: {len(content)}")

    from repositories.writing_tasks_repository import update_writing_task, add_writing_task
    update_writing_task(SOURCE_TASK_ID, polished=content, status="completed", progress=100)
    print(f"源任务 {SOURCE_TASK_ID} polished 已写入")

    # ── 2. 创建 apply 任务并同步执行 ──
    task = add_writing_task(SCRIPT_ID, CHAPTER_INDEX, "apply",
                            prompt=f"应用任务{SOURCE_TASK_ID}的创作结果")
    apply_task_id = task["id"]
    print(f"apply_task_id={apply_task_id}")

    from webnovel.services.webnovel_service import WebnovelService
    svc = WebnovelService()
    await svc._execute_apply_workflow(apply_task_id, SCRIPT_ID, CHAPTER_INDEX, SOURCE_TASK_ID)
    print("apply 工作流执行完成")

    # ── 3. 验证落库 ──
    import sqlite3
    db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
    cur = db.cursor()
    ch = cur.execute(
        "SELECT id, chapter_index, title, word_count FROM script_chapters WHERE script_id=? AND chapter_index=?",
        (SCRIPT_ID, CHAPTER_INDEX)).fetchone()
    print(f"\n== script_chapters 第{CHAPTER_INDEX}章 ==\n  {ch}")
    meta = cur.execute(
        "SELECT chapter_number, hook_type, hook_content, ending_location, ending_emotion "
        "FROM webnovel_chapter_meta WHERE project_id=93 AND chapter_number=?", (CHAPTER_INDEX,)).fetchone()
    print(f"== meta 第{CHAPTER_INDEX}章 ==\n  {meta}")
    states = cur.execute(
        "SELECT character_name, substr(state_summary,1,30), location FROM webnovel_character_state "
        "WHERE project_id=93 AND chapter_number=? ORDER BY id", (CHAPTER_INDEX,)).fetchall()
    print(f"== character_state 第{CHAPTER_INDEX}章（{len(states)} 条）==")
    for s in states:
        print("  ", s)
    foreshadows = cur.execute(
        "SELECT COUNT(*) FROM webnovel_foreshadow WHERE project_id=93").fetchone()
    print(f"== 伏笔表总数 ==\n  {foreshadows}")
    db.close()


if __name__ == "__main__":
    asyncio.run(main())
