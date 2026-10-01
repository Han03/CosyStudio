# -*- coding: utf-8 -*-
"""智能创作第1章：卷纲补全验证 → 拆章 → 完整write流程 → 创作后数据检查。"""
import sys, asyncio, time, sqlite3
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

from webnovel.repositories import (
    get_webnovel_project_by_script, get_volume_outlines_by_project,
    get_character_cards_by_project, get_golden_finger_by_project,
    get_power_system_by_project, get_worldview_by_project,
    get_character_group_by_project, get_character_group_members,
    get_volume_crises, get_chapter_plans_by_volume,
)
from webnovel.pipeline.executors.plan_executor import PlanExecutor
from webnovel.pipeline.orchestrator import PipelineOrchestrator
from repositories.writing_tasks_repository import add_writing_task

SCRIPT_ID = 999916
DB = r'C:\MyProjects\CosyStudio\data\cache\app.db'
LOGDB = r'C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db'

def q(sql, args=()):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(sql, args)
    rows = cur.fetchall()
    conn.close()
    return rows

def qlog(sql, args=()):
    conn = sqlite3.connect(LOGDB)
    cur = conn.cursor()
    cur.execute(sql, args)
    rows = cur.fetchall()
    conn.close()
    return rows

async def main():
    project = get_webnovel_project_by_script(SCRIPT_ID)
    pid = project['id']
    print(f'项目: id={pid} title={project["title"]}')

    log_start = qlog('SELECT COALESCE(MAX(id),0) FROM llm_call_logs')[0][0]
    print(f'LLM 日志起点 id = {log_start}')

    # 卷1
    outlines = get_volume_outlines_by_project(pid)
    vol1 = next(o for o in outlines if o['volume_number'] == 1)
    print(f'卷1: id={vol1["id"]} {vol1["volume_name"]} [{vol1["chapter_start"]}-{vol1["chapter_end"]}]')
    print(f'  补全前: 节拍字段已填={sum(1 for f in PlanExecutor.BEAT_FIELDS if vol1.get(f))}/{len(PlanExecutor.BEAT_FIELDS)}, crises={len(get_volume_crises(vol1["id"]))}')

    # ── 1. 拆章前卷纲细节补全（本次改造核心验证）──
    executor = PlanExecutor(SCRIPT_ID, 0, 0)
    protagonist = get_character_cards_by_project(pid, 'protagonist')[0]
    cg = get_character_group_by_project(pid)
    cgm = get_character_group_members(cg['id']) if cg else []
    t0 = time.time()
    outline = await executor._ensure_volume_detail(
        project, vol1, protagonist,
        get_golden_finger_by_project(pid), get_power_system_by_project(pid),
        get_worldview_by_project(pid), 1,
        char_group=cg, char_group_members=cgm
    )
    print(f'卷纲补全: {time.time()-t0:.1f}s')
    print(f'  补全后: 节拍字段已填={sum(1 for f in executor.BEAT_FIELDS if outline.get(f))}/{len(executor.BEAT_FIELDS)}, crises={len(get_volume_crises(vol1["id"]))}')
    print(f'  骨架继承: 卷名={outline["volume_name"]}')
    print(f'    核心冲突={str(outline.get("core_conflict"))[:40]}')
    print(f'    卷末高潮={str(outline.get("volume_climax"))[:40]}')
    print(f'    节拍样例 catalyst_event={str(outline.get("catalyst_event"))[:40]}')
    print(f'    节拍样例 protagonist_goal={str(outline.get("protagonist_goal"))[:40]}')

    # ── 2. 拆章第1章 ──
    t0 = time.time()
    plans = await executor._generate_chapter_plans(
        project, outline, protagonist, 1,
        start_chapter=1, end_chapter=1,
        char_group=cg, char_group_members=cgm
    )
    n = executor._save_chapter_plans(vol1['id'], plans) if plans else 0
    print(f'拆章第1章: {n} 章规划, 耗时={time.time()-t0:.1f}s')
    saved = get_chapter_plans_by_volume(vol1['id'])
    if saved:
        p1 = saved[0]
        print(f'  第1章规划: summary={str(p1.get("summary"))[:50]}')

    # ── 3. 智能创作完整流程（write 6 步）──
    task = add_writing_task(SCRIPT_ID, 1, "write")
    task_id = task['id']
    orch = PipelineOrchestrator(SCRIPT_ID, 1, task_id)
    t0 = time.time()
    result = await orch.execute_workflow("write", {"chapter_index": 1, "chapter_words": 0})
    elapsed = time.time() - t0
    print(f'\n智能创作第1章: success={result["success"]} 耗时={elapsed:.1f}s')
    if not result["success"]:
        print(f'失败: {result.get("error_message")}')
        return

    ctx = result.get('context', {})
    draft = ctx.get('draft', '') or ctx.get('draft_content', '')
    polished = ctx.get('polished', '') or ctx.get('polished_content', '')
    plot = ctx.get('plot', '') or ctx.get('chapter_plot', '')
    print(f'  剧情: {len(str(plot))} 字')
    print(f'  草稿: {len(str(draft))} 字')
    print(f'  润色: {len(str(polished))} 字')

    log_end = qlog('SELECT COALESCE(MAX(id),0) FROM llm_call_logs')[0][0]
    print(f'LLM 日志区间: {log_start+1} - {log_end} (共{log_end-log_start}条)')

    # ── 4. 创作后数据检查 ──
    print(f'\n===== [创作后] 业务数据检查 =====')
    checks = [
        ('webnovel_chapter_plot', f'SELECT COUNT(*) FROM webnovel_chapter_plot WHERE project_id={pid}'),
        ('webnovel_chapter_plan(第1章)', f'SELECT COUNT(*) FROM webnovel_chapter_plan WHERE volume_outline_id={vol1["id"]} AND chapter_index=1'),
        ('webnovel_chapter_content', f'SELECT COUNT(*) FROM webnovel_chapter_content WHERE project_id={pid} AND chapter_index=1'),
        ('webnovel_chapter_meta', f'SELECT COUNT(*) FROM webnovel_chapter_meta WHERE project_id={pid} AND chapter_index=1'),
        ('webnovel_character_state', f'SELECT COUNT(*) FROM webnovel_character_state WHERE project_id={pid}'),
        ('webnovel_character_item', f'SELECT COUNT(*) FROM webnovel_character_item WHERE project_id={pid}'),
        ('webnovel_timeline', f'SELECT COUNT(*) FROM webnovel_timeline WHERE project_id={pid}'),
        ('webnovel_timeline_chapter', f'SELECT COUNT(*) FROM webnovel_timeline_chapter WHERE chapter_index=1'),
        ('webnovel_open_loops', f'SELECT COUNT(*) FROM webnovel_open_loops WHERE project_id={pid}'),
        ('webnovel_foreshadow', f'SELECT COUNT(*) FROM webnovel_foreshadow WHERE project_id={pid}'),
        ('webnovel_volume_crisis(补全后)', f'SELECT COUNT(*) FROM webnovel_volume_crisis WHERE volume_outline_id={vol1["id"]}'),
        ('webnovel_chapter_review', f'SELECT COUNT(*) FROM webnovel_chapter_review WHERE project_id={pid} AND chapter_index=1'),
    ]
    for name, sql in checks:
        try:
            cnt = q(sql)[0][0]
            flag = 'OK ' if cnt > 0 else '-- '
            print(f'  {flag}{name}: {cnt}')
        except Exception as e:
            print(f'  ?? {name}: {e}')

    # 章节正文详情
    rows = q(f'SELECT chapter_index, length(content), length(plot_outline) FROM webnovel_chapter_content WHERE project_id={pid} AND chapter_index=1')
    if rows:
        print(f'  章节正文: 正文{rows[0][1]}字 剧情大纲{rows[0][2]}字')
    rows2 = q(f'SELECT current_chapter, total_words, current_volume FROM webnovel_state WHERE project_id={pid}')
    if rows2:
        print(f'  写作状态: 当前章={rows2[0][0]} 总字数={rows2[0][1]} 当前卷={rows2[0][2]}')

if __name__ == '__main__':
    asyncio.run(main())
