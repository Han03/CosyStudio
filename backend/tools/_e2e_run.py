# -*- coding: utf-8 -*-
"""全链路验证：跑「全家穿越明末啦」第3章完整 write 流程。

- 清除第3章剧情缓存（强制走剧情生成）
- 设置 chapter_words=4000 验证字数参数化接通
- 跑 context_builder → plot_generator → plot_reviewer → draft_generator → draft_reviewer → draft_polisher → setting_recorder
"""
import asyncio
import os
import sys
import sqlite3
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SCRIPT_ID = 999913
PROJECT_ID = 93
CHAPTER_INDEX = int(os.environ.get("CH_INDEX", "4"))


def clear_plot_cache():
    db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app.db")
    cur = db.cursor()
    cur.execute("DELETE FROM webnovel_chapter_plot WHERE project_id=? AND chapter_index=?", (PROJECT_ID, CHAPTER_INDEX))
    db.commit()
    n = cur.rowcount
    db.close()
    print(f"已清除第{CHAPTER_INDEX}章剧情缓存: {n} 条")


def create_task():
    from repositories.writing_tasks_repository import add_writing_task
    task = add_writing_task(
        script_id=SCRIPT_ID,
        chapter_index=CHAPTER_INDEX,
        task_type="continue",
        prompt="",
    )
    return task["id"]


async def main():
    clear_plot_cache()
    task_id = create_task()
    print(f"task_id={task_id}")

    from webnovel.pipeline.orchestrator import PipelineOrchestrator

    orch = PipelineOrchestrator(script_id=SCRIPT_ID, chapter_index=CHAPTER_INDEX, task_id=task_id)
    # 字数参数化：目标成品 4000 字
    orch._context["chapter_words"] = 4000

    steps = [
        "context_builder",
        "chapter_plot_generator",
        "chapter_plot_reviewer",
        "draft_generator",
        "draft_reviewer",
        "draft_polisher",
        "setting_recorder",
    ]

    result = await orch.execute_pipeline(steps, user_prompt="")
    print("\n== 结果 ==")
    print("success:", result["success"])
    print("completed:", result["completed_steps"], "/", result["total_steps"])
    print("failed:", result["failed_steps"])

    for entry in result.get("execution_log", []):
        print(f"  {entry['step']}: success={entry['success']} | {entry.get('summary', '')} | err={entry.get('error', '')[:120]}")

    ctx = result.get("context", {})
    word_cfg = ctx.get("word_config", {})
    print("\nword_config:", word_cfg)

    draft = ctx.get("draft_content", "")
    polished = ctx.get("polished_content", "")
    print(f"草稿字数: {len(draft)} | 成品字数: {len(polished)}")

    if polished:
        out = os.path.join(os.path.dirname(__file__), "_e2e_polished.txt")
        with open(out, "w", encoding="utf-8") as f:
            f.write(polished)
        print(f"成品已存: {out}")

    # 诊断输出：各节点装配上下文长度
    print("\n== 上下文装配诊断（从日志/step_ctx 取） ==")
    # 打印 analysis 选择记录
    print("step_selections:", json.dumps(ctx.get("step_selections", {}), ensure_ascii=False)[:800])


if __name__ == "__main__":
    asyncio.run(main())
