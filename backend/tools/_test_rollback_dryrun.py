# 一次性回退干跑验证：对 9 张关联表做"插入临时数据 → 调用删除/恢复函数 → 断言 → 快照恢复"
# 运行：python tools/_test_rollback_dryrun.py
import json
import sqlite3
import sys
import time

sys.path.insert(0, '.')
DB = r'C:\MyProjects\CosyStudio\data\cache\app.db'
PROJECT_ID = 93
CH = 999  # 临时章号，避开真实章节

TABLES = [
    'webnovel_open_loops', 'webnovel_timeline_countdown', 'webnovel_cool_points',
    'webnovel_character_state', 'webnovel_worldview_setting',
    'webnovel_character_relationship', 'webnovel_character_growth',
    'webnovel_character_item', 'webnovel_character_card',
]


def snapshot(conn) -> dict:
    """全表行快照（保留原 id 以支持恢复）。"""
    snap = {}
    for t in TABLES:
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info({t})')]
        rows = [dict(zip(cols, r)) for r in conn.execute(f'SELECT * FROM {t}')]
        snap[t] = {'cols': cols, 'rows': rows}
    return snap


def restore(conn, snap):
    """清空表后按快照重插恢复。"""
    for t, data in snap.items():
        conn.execute(f'DELETE FROM {t}')
        cols = data['cols']
        placeholders = ','.join('?' * len(cols))
        for row in data['rows']:
            conn.execute(
                f'INSERT INTO {t} ({",".join(cols)}) VALUES ({placeholders})',
                [row[c] for c in cols]
            )
    conn.commit()


def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    snap = snapshot(conn)
    ok = True
    try:
        now = time.time()
        # 准备角色卡（临时）
        cur.execute(
            """INSERT INTO webnovel_character_card (project_id, name, character_type, alias, identity)
               VALUES (?, ?, 'supporting', '', '')""",
            (PROJECT_ID, f'回退测试卡{CH}')
        )
        cid = cur.lastrowid
        # 关系 / 成长 / 物品
        cur.execute(
            """INSERT INTO webnovel_character_relationship
               (character_id, relation_type, target_character_id, target_name, description, source_chapter)
               VALUES (?, '关系', ?, '目标', '回退测试', ?)""",
            (cid, cid, CH)
        )
        cur.execute(
            """INSERT INTO webnovel_character_growth
               (character_id, stage, description, source_chapter)
               VALUES (?, '第999章', '回退测试', ?)""",
            (cid, CH)
        )
        cur.execute(
            """INSERT INTO webnovel_character_item
               (character_id, item_name, quantity, acquired_chapter, lost_chapter)
               VALUES (?, '回退测试物品', 3, ?, 0)""",
            (cid, CH)
        )
        cur.execute(
            """INSERT INTO webnovel_character_item
               (character_id, item_name, quantity, acquired_chapter, lost_chapter)
               VALUES (?, '回退测试失去物', 2, 0, ?)""",
            (cid, CH)
        )
        # 开放悬念（埋设/回收各一条）
        cur.execute(
            """INSERT INTO webnovel_open_loops (project_id, content, status, planted_chapter, resolved_chapter)
               VALUES (?, '回退测试埋设', 'active', ?, 0)""",
            (PROJECT_ID, CH)
        )
        cur.execute(
            """INSERT INTO webnovel_open_loops (project_id, content, status, planted_chapter, resolved_chapter)
               VALUES (?, '回退测试回收', 'resolved', 0, ?)""",
            (PROJECT_ID, CH)
        )
        # 倒计时（埋设/触发各一条）——需要 timeline
        cur.execute("SELECT id FROM webnovel_timeline WHERE project_id = ? LIMIT 1", (PROJECT_ID,))
        tl_row = cur.fetchone()
        if tl_row:
            tl_id = tl_row['id']
            cur.execute(
                """INSERT INTO webnovel_timeline_countdown
                   (timeline_id, event_name, current_status, project_id, planted_chapter, trigger_chapter)
                   VALUES (?, '回退测试埋设', '未触发', ?, ?, 0)""",
                (tl_id, PROJECT_ID, CH)
            )
            cur.execute(
                """INSERT INTO webnovel_timeline_countdown
                   (timeline_id, event_name, current_status, project_id, planted_chapter, trigger_chapter)
                   VALUES (?, '回退测试触发', '已触发', ?, 0, ?)""",
                (tl_id, PROJECT_ID, CH)
            )
        # 爽点 / 状态 / 世界观
        cur.execute(
            """INSERT INTO webnovel_cool_points (project_id, chapter_number, content)
               VALUES (?, ?, '回退测试爽点')""",
            (PROJECT_ID, CH)
        )
        cur.execute(
            """INSERT INTO webnovel_character_state (project_id, character_id, chapter_number, state_summary)
               VALUES (?, ?, ?, '回退测试状态')""",
            (PROJECT_ID, cid, CH)
        )
        cur.execute(
            """INSERT INTO webnovel_worldview_setting (project_id, chapter_number, name, content, category)
               VALUES (?, ?, '回退测试设定', '回退测试内容', '测试')""",
            (PROJECT_ID, CH)
        )
        conn.commit()

        from webnovel.repositories import (
            delete_open_loops_by_planted_chapter, restore_open_loops_by_resolved_chapter,
            delete_timeline_countdowns_by_planted_chapter, restore_timeline_countdowns_by_trigger_chapter,
            delete_cool_points_by_chapter, delete_character_states_by_chapter,
            delete_worldview_settings_by_chapter, delete_relationships_by_chapter,
            delete_growths_by_chapter, delete_items_acquired_in_chapter,
            restore_items_lost_in_chapter, delete_character_card,
            update_character_card, get_character_card,
            add_setting_change, add_worldview_setting,
        )

        def expect(name, got, want):
            nonlocal ok
            status = 'PASS' if got == want else f'FAIL (got {got}, want {want})'
            print(f'  [{status}] {name}')
            if got != want:
                ok = False

        print('== 开放悬念 ==')
        expect('delete_open_loops_by_planted_chapter', delete_open_loops_by_planted_chapter(PROJECT_ID, CH), 1)
        expect('restore_open_loops_by_resolved_chapter', restore_open_loops_by_resolved_chapter(PROJECT_ID, CH), 1)
        print('== 倒计时 ==')
        expect('delete_timeline_countdowns_by_planted_chapter',
               delete_timeline_countdowns_by_planted_chapter(PROJECT_ID, CH), 1)
        expect('restore_timeline_countdowns_by_trigger_chapter',
               restore_timeline_countdowns_by_trigger_chapter(PROJECT_ID, CH), 1)
        print('== 直接删除 ==')
        expect('delete_cool_points_by_chapter', delete_cool_points_by_chapter(PROJECT_ID, CH), 1)
        expect('delete_character_states_by_chapter', delete_character_states_by_chapter(PROJECT_ID, CH), 1)
        expect('delete_worldview_settings_by_chapter', delete_worldview_settings_by_chapter(PROJECT_ID, CH), 1)
        expect('delete_relationships_by_chapter', delete_relationships_by_chapter(PROJECT_ID, CH), 1)
        expect('delete_growths_by_chapter', delete_growths_by_chapter(PROJECT_ID, CH), 1)
        print('== 物品 ==')
        expect('delete_items_acquired_in_chapter', delete_items_acquired_in_chapter(PROJECT_ID, CH), 1)
        expect('restore_items_lost_in_chapter', restore_items_lost_in_chapter(PROJECT_ID, CH), 1)
        print('== 基础设定变更回退 ==')
        # update_ability：改值并记录，回退还原（卡片尚在）
        update_character_card(cid, ability_limit='旧能力')
        add_setting_change(PROJECT_ID, CH, 'character_card', cid, 'update_ability',
                           json.dumps({'ability_limit': '旧能力'}, ensure_ascii=False),
                           json.dumps({'ability_limit': '新能力'}, ensure_ascii=False))
        update_character_card(cid, ability_limit='新能力')
        from webnovel.repositories import get_setting_changes_by_chapter
        chs = get_setting_changes_by_chapter(PROJECT_ID, CH)
        ability_change = next((c for c in chs if c['change_type'] == 'update_ability'), None)
        if ability_change:
            bd = json.loads(ability_change['before_data'])
            update_character_card(cid, ability_limit=bd['ability_limit'])
            card = get_character_card(PROJECT_ID, cid)
            expect('update_ability 回退还原', (card or {}).get('ability_limit'), '旧能力')
        else:
            expect('update_ability 记录存在', False, True)
            ok = False
        # create：建卡并记录，回退删卡
        add_setting_change(PROJECT_ID, CH, 'character_card', cid, 'create', '', '{}')
        expect('create 回退删卡', 1 if delete_character_card(cid) else 0, 1)
        print('== 世界观设定独立写入 ==')
        add_worldview_setting(PROJECT_ID, CH, '回退测试设定2', '内容2', '测试')
        expect('delete_worldview_settings_by_chapter(二次)',
               delete_worldview_settings_by_chapter(PROJECT_ID, CH), 1)

    except Exception as e:
        import traceback
        traceback.print_exc()
        ok = False

    finally:
        restore(conn, snap)
        conn.close()
        print(f'\n快照已恢复，临时数据已清理。结果：{"全部 PASS" if ok else "存在 FAIL"}')
        sys.exit(0 if ok else 1)


if __name__ == '__main__':
    run()
