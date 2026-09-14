# 实测：删除章节 = 取消应用结果（project 93 / 第 4 章）
import asyncio
import json
import os
import sqlite3
import sys

sys.path.insert(0, '.')
SCRIPT_ID = 999913
CH = 4  # 目标章节（实测时按需修改）
DB = r'C:\MyProjects\CosyStudio\data\cache\app.db'


def db_counts():
    out = {}
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    cur = db.cursor()
    checks = [
        ('script_chapters', 'SELECT COUNT(*) AS n FROM script_chapters WHERE script_id=? AND chapter_index=?', (SCRIPT_ID, CH)),
        ('script_lines', 'SELECT COUNT(*) AS n FROM script_lines WHERE script_id=? AND chapter_index=?', (SCRIPT_ID, CH)),
        ('character_state', 'SELECT COUNT(*) AS n FROM webnovel_character_state WHERE project_id=93 AND chapter_number=?', (CH,)),
        ('cool_points', 'SELECT COUNT(*) AS n FROM webnovel_cool_points WHERE project_id=93 AND chapter_number=?', (CH,)),
        ('worldview_setting', 'SELECT COUNT(*) AS n FROM webnovel_worldview_setting WHERE project_id=93 AND chapter_number=?', (CH,)),
        ('setting_change', 'SELECT COUNT(*) AS n FROM webnovel_setting_change WHERE project_id=93 AND chapter_number=?', (CH,)),
        ('open_loops_planted', 'SELECT COUNT(*) AS n FROM webnovel_open_loops WHERE project_id=93 AND planted_chapter=?', (CH,)),
        ('open_loops_resolved', 'SELECT COUNT(*) AS n FROM webnovel_open_loops WHERE project_id=93 AND resolved_chapter=?', (CH,)),
        ('chapter_meta', 'SELECT COUNT(*) AS n FROM webnovel_chapter_meta WHERE project_id=93 AND chapter_number=?', (CH,)),
        ('review_record', 'SELECT COUNT(*) AS n FROM webnovel_review_record WHERE project_id=93 AND chapter_number=?', (CH,)),
        ('chapter_plot', 'SELECT COUNT(*) AS n FROM webnovel_chapter_plot WHERE project_id=93 AND chapter_index=?', (CH,)),
        ('pipeline_logs', 'SELECT COUNT(*) AS n FROM script_writing_pipeline_logs WHERE script_id=? AND chapter_index=?', (SCRIPT_ID, CH)),
        ('timeline_chapter', 'SELECT COUNT(*) AS n FROM webnovel_timeline_chapter WHERE timeline_id IN (SELECT id FROM webnovel_timeline WHERE project_id=93) AND chapter_number=?', (CH,)),
        ('relationships', 'SELECT COUNT(*) AS n FROM webnovel_character_relationship WHERE character_id IN (SELECT id FROM webnovel_character_card WHERE project_id=93) AND source_chapter=?', (CH,)),
        ('growths', 'SELECT COUNT(*) AS n FROM webnovel_character_growth WHERE character_id IN (SELECT id FROM webnovel_character_card WHERE project_id=93) AND source_chapter=?', (CH,)),
        ('items', 'SELECT COUNT(*) AS n FROM webnovel_character_item WHERE character_id IN (SELECT id FROM webnovel_character_card WHERE project_id=93) AND (acquired_chapter=? OR lost_chapter=?)', (CH, CH)),
    ]
    for name, sql, args in checks:
        cur.execute(sql, args)
        out[name] = cur.fetchone()['n']
    # 章节文件
    cur.execute('SELECT file_path FROM script_chapters WHERE script_id=? AND chapter_index=?', (SCRIPT_ID, CH))
    row = cur.fetchone()
    out['chapter_file'] = row['file_path'] if row else None
    db.close()
    return out


def chapter_file_exists(path):
    if not path:
        return None
    return os.path.exists(path)


async def main():
    from webnovel.repositories import get_webnovel_project_by_script
    get_webnovel_project_by_script(SCRIPT_ID)

    before = db_counts()
    print('=== 删除前 ===')
    for k, v in before.items():
        print(f'  {k}: {v}')

    from webnovel.services.webnovel_service import get_webnovel_service
    svc = get_webnovel_service()
    result = await svc.rollback_apply_by_chapter(SCRIPT_ID, CH)
    print('\n=== rollback 结果 ===')
    print(json.dumps(result, ensure_ascii=False, indent=2))

    after = db_counts()
    print('\n=== 删除后 ===')
    for k, v in after.items():
        print(f'  {k}: {v}')

    # 校验
    print('\n=== 校验 ===')
    ok = True
    for k in before:
        if k == 'chapter_file':
            continue
        if after[k] != 0:
            print(f'  [FAIL] {k} 残留 {after[k]}')
            ok = False
    if before['chapter_file'] and after['chapter_file'] is None:
        print('  [PASS] 章节行已删除')
    elif after['chapter_file'] is None:
        print('  [PASS] 章节行不存在（删除前即无）')
    else:
        print('  [FAIL] 章节行仍存在')
        ok = False
    # 其他章还在
    db = sqlite3.connect(DB)
    cur = db.cursor()
    cur.execute('SELECT COUNT(*) FROM script_chapters WHERE script_id=?', (SCRIPT_ID,))
    left = cur.fetchone()[0]
    db.close()
    print(f'  [INFO] 剩余章节数: {left}')
    print(f'\n结果: {"全部通过" if ok else "存在 FAIL"}')


asyncio.run(main())
