# 实测：chapter_meta 插入化（get 取最新 / list 每章最新 / 多版本保留 / 按章删除）
import sqlite3
import sys

sys.path.insert(0, '.')
DB = r'C:\MyProjects\CosyStudio\data\cache\app.db'
PROJECT_ID = 93
CH = 777  # 临时章号


def cleanup():
    db = sqlite3.connect(DB)
    db.execute('DELETE FROM webnovel_chapter_meta WHERE project_id=? AND chapter_number=?', (PROJECT_ID, CH))
    db.execute('DELETE FROM webnovel_chapter_meta WHERE project_id=? AND chapter_number=?', (PROJECT_ID, CH + 1))
    db.commit()
    db.close()


def run():
    cleanup()
    from webnovel.repositories import (
        get_webnovel_project_by_script, add_chapter_meta, get_chapter_meta,
        get_chapter_meta_list, delete_chapter_meta,
    )
    get_webnovel_project_by_script(999913)

    ok = True

    def expect(name, got, want):
        nonlocal ok
        status = 'PASS' if got == want else f'FAIL (got {got!r}, want {want!r})'
        print(f'  [{status}] {name}')
        if got != want:
            ok = False

    print('== 模拟两次应用结果（同章插入两版）==')
    # 第一次应用结果：hook_type 为 LLM 值
    add_chapter_meta(PROJECT_ID, CH, hook_type='悬念式', hook_content='破庙外传来马蹄声，是谁？',
                     hook_strength='强', hook_pattern='悬念留白', ending_emotion='期待',
                     ending_time='深夜', ending_location='破庙')
    # 第二次应用结果：新版本
    add_chapter_meta(PROJECT_ID, CH, hook_type='冲突式', hook_content='黑衣人掀开兜帽，竟是她。',
                     hook_strength='强', hook_pattern='反转', ending_emotion='紧张',
                     ending_time='黎明', ending_location='破庙外')

    # 未创作章：无 meta
    expect('未创作章 get=None', get_chapter_meta(PROJECT_ID, CH + 1), None)

    m = get_chapter_meta(PROJECT_ID, CH)
    expect('get 取最新（hook_content=反转版）', m['hook_content'], '黑衣人掀开兜帽，竟是她。')
    expect('get 取最新（hook_type=冲突式）', m['hook_type'], '冲突式')

    lst = get_chapter_meta_list(PROJECT_ID)
    rows_ch = [r for r in lst if r['chapter_number'] == CH]
    expect('list 每章一条', len(rows_ch), 1)
    expect('list 取最新', rows_ch[0]['hook_content'], '黑衣人掀开兜帽，竟是她。')

    # 数据库里两版都在（历史保留）
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    cur = db.cursor()
    cur.execute('SELECT COUNT(*) AS n FROM webnovel_chapter_meta WHERE project_id=? AND chapter_number=?', (PROJECT_ID, CH))
    expect('历史版本保留（2 行）', cur.fetchone()['n'], 2)
    db.close()

    print('== 按章删除（取消应用结果语义：清全部版本）==')
    expect('delete_chapter_meta', delete_chapter_meta(PROJECT_ID, CH), 2)
    expect('删除后 get=None', get_chapter_meta(PROJECT_ID, CH), None)

    cleanup()
    print(f'\n结果: {"全部 PASS" if ok else "存在 FAIL"}')
    sys.exit(0 if ok else 1)


run()
