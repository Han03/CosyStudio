# -*- coding: utf-8 -*-
"""第4章重跑：清除数据 → 智能创作（真实服务链路）→ 应用结果 → 换行符验证。

- 清除：script_writing_tasks ch4 / chapter_plot ch4 / script_chapters ch4 /
        chapter_meta ch4 / review_record ch4 / character_state ch4 / cool_points ch4 /
        open_loops(planted=4) / pipeline_logs ch4 / 章节文件 4.txt
- 创作：add continue 任务 → svc._execute_writing_workflow（大纲检查→write 流程→落库 completed）
- 应用：add apply 任务 → svc._execute_apply_workflow（保存章节+事实+RAG）
- 验证：源任务 polished / 章节文件 正文 的换行符形态（字面\\n=0，真实换行>0）
"""
import asyncio
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

SCRIPT_ID = 999913
PROJECT_ID = 93
CH = 4
DB = r"C:\MyProjects\CosyStudio\data\cache\app.db"
CH_FILE = rf"C:\MyProjects\CosyStudio\media\document\scripts\{SCRIPT_ID}\chapters\{CH}.txt"


def clear_ch4():
    """清除第4章数据，返回删除统计。"""
    db = sqlite3.connect(DB)
    cur = db.cursor()
    ops = [
        ("script_writing_tasks", "DELETE FROM script_writing_tasks WHERE script_id=? AND chapter_index=?", (SCRIPT_ID, CH)),
        ("webnovel_chapter_plot", "DELETE FROM webnovel_chapter_plot WHERE project_id=? AND chapter_index=?", (PROJECT_ID, CH)),
        ("script_chapters", "DELETE FROM script_chapters WHERE script_id=? AND chapter_index=?", (SCRIPT_ID, CH)),
        ("webnovel_chapter_meta", "DELETE FROM webnovel_chapter_meta WHERE project_id=? AND chapter_number=?", (PROJECT_ID, CH)),
        ("webnovel_review_record", "DELETE FROM webnovel_review_record WHERE project_id=? AND chapter_number=?", (PROJECT_ID, CH)),
        ("webnovel_character_state", "DELETE FROM webnovel_character_state WHERE project_id=? AND chapter_number=?", (PROJECT_ID, CH)),
        ("webnovel_cool_points", "DELETE FROM webnovel_cool_points WHERE project_id=? AND chapter_number=?", (PROJECT_ID, CH)),
        ("webnovel_open_loops", "DELETE FROM webnovel_open_loops WHERE project_id=? AND planted_chapter=?", (PROJECT_ID, CH)),
        ("script_writing_pipeline_logs", "DELETE FROM script_writing_pipeline_logs WHERE script_id=? AND chapter_index=?", (SCRIPT_ID, CH)),
    ]
    stats = {}
    for name, sql, params in ops:
        try:
            cur.execute(sql, params)
            stats[name] = cur.rowcount
        except Exception as e:
            stats[name] = f"err:{e}"
    db.commit()
    db.close()
    if os.path.exists(CH_FILE):
        try:
            os.remove(CH_FILE)
            stats["章节文件4.txt"] = "已删除"
        except Exception as e:
            stats["章节文件4.txt"] = f"err:{e}"
    else:
        stats["章节文件4.txt"] = "不存在(跳过)"
    return stats


def newline_check(name, text):
    lit = text.count("\\n")
    real = text.count("\n")
    ok = lit == 0 and real > 0
    print(f"  [{'OK' if ok else 'FAIL'}] {name}: len={len(text)} 字面\\n={lit} 真实换行={real}")
    return ok


async def main():
    print("===== 1. 清除第4章数据 =====")
    stats = clear_ch4()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print("\n===== 2. 智能创作（真实服务链路）=====")
    from repositories.writing_tasks_repository import add_writing_task
    from webnovel.services.webnovel_service import WebnovelService

    task = add_writing_task(SCRIPT_ID, CH, "continue", prompt="重跑第4章验证换行符")
    write_task_id = task["id"]
    print(f"continue_task_id={write_task_id}")

    svc = WebnovelService()
    await svc._execute_writing_workflow(write_task_id, enable_polish=True, auto_apply=False)
    print("创作工作流执行完成")

    from repositories.writing_tasks_repository import get_writing_task
    wt = get_writing_task(None, write_task_id)
    print(f"创作任务状态: {wt['status']} progress={wt['progress']} {wt.get('progress_message')}")
    if wt["status"] != "completed":
        print(f"创作失败: {wt.get('error_message')}")
        return
    polished = wt.get("polished", "")
    print(f"成品字数: {len(polished)}")

    print("\n===== 3. 应用结果 =====")
    apply_task = add_writing_task(SCRIPT_ID, CH, "apply", prompt=f"应用任务{write_task_id}的创作结果")
    apply_task_id = apply_task["id"]
    print(f"apply_task_id={apply_task_id}")
    await svc._execute_apply_workflow(apply_task_id, SCRIPT_ID, CH, write_task_id)
    at = get_writing_task(None, apply_task_id)
    print(f"apply 任务状态: {at['status']} {at.get('progress_message')}")

    print("\n===== 4. 换行符验证 =====")
    ok_all = True
    ok_all &= newline_check("源任务 polished", polished)
    draft = wt.get("draft", "")
    ok_all &= newline_check("源任务 draft", draft) if draft else True
    if os.path.exists(CH_FILE):
        with open(CH_FILE, encoding="utf-8") as f:
            ch_content = f.read()
        ok_all &= newline_check(f"章节文件 {CH}.txt", ch_content)
    else:
        print("  [FAIL] 章节文件不存在:", CH_FILE)
        ok_all = False

    # 成品留存
    out = os.path.join(os.path.dirname(__file__), "_e2e_polished.txt")
    if polished:
        with open(out, "w", encoding="utf-8") as f:
            f.write(polished)
        print(f"\n成品已存: {out}")

    # 章节元数据
    db = sqlite3.connect(DB)
    cur = db.cursor()
    ch = cur.execute(
        "SELECT id, chapter_index, title, file_path, word_count FROM script_chapters "
        "WHERE script_id=? AND chapter_index=?", (SCRIPT_ID, CH)).fetchone()
    print("\nscript_chapters ch4:", ch)
    meta = cur.execute(
        "SELECT chapter_number, hook_type, hook_content FROM webnovel_chapter_meta "
        "WHERE project_id=? AND chapter_number=?", (PROJECT_ID, CH)).fetchone()
    print("chapter_meta ch4:", meta)
    db.close()

    print("\n===== 结论 =====", "全部通过" if ok_all else "存在失败项")


if __name__ == "__main__":
    asyncio.run(main())
