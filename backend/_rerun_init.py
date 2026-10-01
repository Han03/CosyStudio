# -*- coding: utf-8 -*-
"""重跑凡人修仙传(999916)深度初始化 + 业务数据齐全性检查。"""
import sys, asyncio, time, sqlite3, json, os
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

from repositories.script_repository import update_script
from webnovel.repositories import (
    delete_webnovel_project_by_script, get_webnovel_project_by_script,
)
from webnovel.repositories.init_session_repository import get_all_init_data, complete_init_session
from webnovel.api.init_routes import _merge_all_data
from webnovel.pipeline.executors.init_executor import InitExecutor
from webnovel.services.webnovel_service import get_webnovel_service

SCRIPT_ID = 999916
SESSION_ID = 68
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

def check_init_data(project_id: int, stage: str):
    """初始化后业务数据齐全性检查。"""
    print(f'\n===== [{stage}] 业务数据检查 =====')
    checks = [
        ('webnovel_project', f'SELECT COUNT(*) FROM webnovel_project WHERE id={project_id}'),
        ('webnovel_worldview', f'SELECT COUNT(*) FROM webnovel_worldview WHERE project_id={project_id}'),
        ('webnovel_worldview_faction', f'SELECT COUNT(*) FROM webnovel_worldview_faction WHERE worldview_id IN (SELECT id FROM webnovel_worldview WHERE project_id={project_id})'),
        ('webnovel_worldview_history', f'SELECT COUNT(*) FROM webnovel_worldview_history WHERE worldview_id IN (SELECT id FROM webnovel_worldview WHERE project_id={project_id})'),
        ('webnovel_golden_finger', f'SELECT COUNT(*) FROM webnovel_golden_finger WHERE project_id={project_id}'),
        ('webnovel_golden_finger_upgrade', f'SELECT COUNT(*) FROM webnovel_golden_finger_upgrade WHERE golden_finger_id IN (SELECT id FROM webnovel_golden_finger WHERE project_id={project_id})'),
        ('webnovel_golden_finger_payoff', f'SELECT COUNT(*) FROM webnovel_golden_finger_payoff WHERE golden_finger_id IN (SELECT id FROM webnovel_golden_finger WHERE project_id={project_id})'),
        ('webnovel_golden_finger_feedback', f'SELECT COUNT(*) FROM webnovel_golden_finger_feedback WHERE golden_finger_id IN (SELECT id FROM webnovel_golden_finger WHERE project_id={project_id})'),
        ('webnovel_character_card', f'SELECT COUNT(*) FROM webnovel_character_card WHERE project_id={project_id}'),
        ('webnovel_character_growth', f'SELECT COUNT(*) FROM webnovel_character_growth WHERE character_id IN (SELECT id FROM webnovel_character_card WHERE project_id={project_id})'),
        ('webnovel_character_relationship', f'SELECT COUNT(*) FROM webnovel_character_relationship WHERE character_id IN (SELECT id FROM webnovel_character_card WHERE project_id={project_id})'),
        ('webnovel_character_power', f'SELECT COUNT(*) FROM webnovel_character_power WHERE character_id IN (SELECT id FROM webnovel_character_card WHERE project_id={project_id})'),
        ('webnovel_villain', f'SELECT COUNT(*) FROM webnovel_villain WHERE project_id={project_id}'),
        ('webnovel_villain_hierarchy', f'SELECT COUNT(*) FROM webnovel_villain_hierarchy WHERE villain_id IN (SELECT id FROM webnovel_villain WHERE project_id={project_id})'),
        ('webnovel_villain_plot_node', f'SELECT COUNT(*) FROM webnovel_villain_plot_node WHERE villain_id IN (SELECT id FROM webnovel_villain WHERE project_id={project_id})'),
        ('webnovel_power_system', f'SELECT COUNT(*) FROM webnovel_power_system WHERE project_id={project_id}'),
        ('webnovel_power_level', f'SELECT COUNT(*) FROM webnovel_power_level WHERE power_system_id IN (SELECT id FROM webnovel_power_system WHERE project_id={project_id})'),
        ('webnovel_power_feedback', f'SELECT COUNT(*) FROM webnovel_power_feedback WHERE power_system_id IN (SELECT id FROM webnovel_power_system WHERE project_id={project_id})'),
        ('webnovel_volume_outline', f'SELECT COUNT(*) FROM webnovel_volume_outline WHERE project_id={project_id}'),
        ('webnovel_volume_crisis', f'SELECT COUNT(*) FROM webnovel_volume_crisis WHERE volume_outline_id IN (SELECT id FROM webnovel_volume_outline WHERE project_id={project_id})'),
        ('webnovel_plot_thread', f'SELECT COUNT(*) FROM webnovel_plot_thread WHERE project_id={project_id}'),
        ('webnovel_character_group', f'SELECT COUNT(*) FROM webnovel_character_group WHERE project_id={project_id}'),
        ('webnovel_character_group_member', f'SELECT COUNT(*) FROM webnovel_character_group_member WHERE group_id IN (SELECT id FROM webnovel_character_group WHERE project_id={project_id})'),
        ('webnovel_character_group_arc', f'SELECT COUNT(*) FROM webnovel_character_group_arc WHERE group_id IN (SELECT id FROM webnovel_character_group WHERE project_id={project_id})'),
        ('webnovel_state', f'SELECT COUNT(*) FROM webnovel_state WHERE project_id={project_id}'),
        ('webnovel_idea_bank', f'SELECT COUNT(*) FROM webnovel_idea_bank WHERE project_id={project_id}'),
        ('webnovel_master_setting', f'SELECT COUNT(*) FROM webnovel_master_setting WHERE project_id={project_id}'),
        ('webnovel_anti_pattern', f'SELECT COUNT(*) FROM webnovel_anti_pattern WHERE project_id={project_id}'),
    ]
    for name, sql in checks:
        try:
            cnt = q(sql)[0][0]
            flag = 'OK ' if cnt > 0 else '!! '
            print(f'  {flag}{name}: {cnt}')
        except Exception as e:
            print(f'  ?? {name}: {e}')

    # 卷纲字段完整性（初始化预期：仅骨架字段）
    print('  -- 卷纲骨架字段检查（初始化预期）:')
    rows = q(f'SELECT id, volume_number, volume_name, chapter_start, chapter_end, core_conflict, volume_climax FROM webnovel_volume_outline WHERE project_id={project_id} ORDER BY volume_number')
    for r in rows:
        print(f'    卷{r[1]} {r[2]} [{r[3]}-{r[4]}] 冲突={bool(r[5])} 高潮={bool(r[6])}')
    # 节拍字段应全空（本次改造：由拆章补全）
    beat_fields = ['promise_types','catalyst_event','irreversible_change','protagonist_goal','mid_reversal','reversal_insight','lowest_point_event','lowest_point_cost','protagonist_choice','payoff_items','new_hook','unresolved_issues']
    filled = q(f'SELECT volume_number, {", ".join(beat_fields)} FROM webnovel_volume_outline WHERE project_id={project_id}')
    for r in filled:
        filled_cnt = sum(1 for v in r[1:] if v and str(v).strip())
        print(f'    卷{r[0]} 节拍字段已填: {filled_cnt}/{len(beat_fields)}')

    # 世界观关键字段
    print('  -- 世界观关键字段:')
    wv = q(f'SELECT world_summary, core_regions, social_hierarchy, political_rules, social_common_sense, important_locations, key_resource_points FROM webnovel_worldview WHERE project_id={project_id}')
    if wv:
        labels = ['world_summary','core_regions','social_hierarchy','political_rules','social_common_sense','important_locations','key_resource_points']
        for l, v in zip(labels, wv[0]):
            s = str(v or '')
            print(f'    {l}: {"OK" if s.strip() else "EMPTY"} ({len(s)}字)')

    # 角色卡类型分布
    print('  -- 角色卡类型:')
    for r in q(f'SELECT character_type, COUNT(*) FROM webnovel_character_card WHERE project_id={project_id} GROUP BY character_type'):
        print(f'    {r[0]}: {r[1]}')

    # 项目约束字段
    print('  -- 项目约束:')
    p = q(f'SELECT anti_trope_rules, core_selling_points, opening_hook, protagonist_flaw, villain_mirror FROM webnovel_project WHERE id={project_id}')
    labels = ['anti_trope_rules','core_selling_points','opening_hook','protagonist_flaw','villain_mirror']
    for l, v in zip(labels, p[0]):
        print(f'    {l}: {"OK" if str(v or "").strip() else "EMPTY"}')

def check_rag_csv(project_id: int):
    """检查 RAG CSV 索引。"""
    print(f'\n===== RAG CSV 检查 =====')
    try:
        from services.vector_store import get_rag_service
        svc = get_rag_service()
        n = svc.count_by_project(project_id) if hasattr(svc, 'count_by_project') else 'N/A'
        print(f'  RAG chunks: {n}')
    except Exception as e:
        print(f'  RAG check fail: {e}')
    # 从 llm 日志角度无法查 RAG，查 csv_pack 表
    try:
        cnt = q(f"SELECT COUNT(*) FROM webnovel_csv_pack WHERE genre LIKE '%修仙%' OR genre LIKE '%修真%'")
        print(f'  webnovel_csv_pack(修仙/修真) 条数: {cnt[0][0]}')
    except Exception as e:
        print(f'  csv_pack fail: {e}')

async def main():
    # 0. LLM 日志起点
    log_start = qlog('SELECT COALESCE(MAX(id),0) FROM llm_call_logs')[0][0]
    print(f'LLM 日志起点 id = {log_start}')

    # 1. 删除旧项目
    delete_webnovel_project_by_script(SCRIPT_ID)
    print('已删除旧项目 (999916)')

    # 2. merge 初始化会话数据
    all_data = get_all_init_data(SESSION_ID)
    merged = _merge_all_data(all_data)
    print(f'merge 完成, project_data 键数: {len(merged)}')

    # 3. 深度初始化
    executor = InitExecutor(SCRIPT_ID, 0, SESSION_ID, progress_callback=None, interrupt_check=lambda: False)
    t0 = time.time()
    result = await executor.execute({"project_data": merged})
    elapsed = time.time() - t0
    print(f'\n初始化完成: success={result.success} 耗时={elapsed:.1f}s')
    if not result.success:
        print(f'初始化失败: {result.error_message}')
        return

    project = get_webnovel_project_by_script(SCRIPT_ID)
    print(f'项目: id={project["id"]} title={project["title"]} genre={project["genre"]}')

    # 4. 完成会话 + 脚本状态
    complete_init_session(SESSION_ID)
    update_script(SCRIPT_ID, status='ready')

    # 5. RAG CSV 索引
    service = get_webnovel_service()
    await service._index_csv_knowledge(project['id'])
    print('RAG CSV 索引完成')

    # 6. LLM 日志结束
    log_end = qlog('SELECT COALESCE(MAX(id),0) FROM llm_call_logs')[0][0]
    print(f'LLM 日志区间: {log_start+1} - {log_end} (共{log_end-log_start}条)')

    # 7. 数据检查
    check_init_data(project['id'], '初始化后')
    check_rag_csv(project['id'])

if __name__ == '__main__':
    asyncio.run(main())
