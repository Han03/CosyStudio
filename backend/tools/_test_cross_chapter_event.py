# 验证：cross_chapter_event_processor_executor 四类识别能力
# 两步走：A 埋设章（新悬念+新倒计时）→ B 回收章（悬念回收+倒计时触发/取消）
# 全程快照备份，结束后自动恢复，不污染 project 93 真实数据。
# 用法: python tools/_test_cross_chapter_event.py
import asyncio
import copy
import sqlite3
import sys

sys.path.insert(0, '.')

from webnovel.pipeline.executors.cross_chapter_event_processor_executor import (
    CrossChapterEventProcessorExecutor,
)
from webnovel.repositories import (
    get_webnovel_project_by_script,
    get_timelines_by_project,
)

SCRIPT_ID = 999913
CHAPTER = 4
CONTENT_FILE = 'tools/_cross_chapter_test_content.md'


def load_contents() -> dict:
    text = open(CONTENT_FILE, encoding='utf-8').read()
    # 按 "## A" / "## B" 分节
    a_start = text.find('## A 埋设章')
    b_start = text.find('## B 回收章')
    assert a_start != -1 and b_start != -1
    # A 从标题行后取正文，去掉段末分隔线
    content_a = text[a_start:b_start]
    content_a = content_a.split('\n', 1)[1].strip()
    content_a = content_a.rsplit('---', 1)[0].strip()
    content_b = text[b_start:]
    if '---' in content_b:
        content_b = content_b.split('---', 1)[1].strip()
    else:
        # B 是文件最后一段：去掉标题行
        content_b = content_b.split('\n', 1)[1].strip()
    return {"A": content_a, "B": content_b}


def snapshot(project_id: int):
    conn = sqlite3.connect(r'C:\MyProjects\CosyStudio\data\cache\app.db')
    conn.row_factory = sqlite3.Row
    loops = [dict(r) for r in conn.execute(
        "SELECT * FROM webnovel_open_loops WHERE project_id = ?", (project_id,))]
    cds = [dict(r) for r in conn.execute(
        "SELECT * FROM webnovel_timeline_countdown")]
    conn.close()
    return loops, cds


def restore(project_id: int, snap):
    loops_before, cds_before = snap
    conn = sqlite3.connect(r'C:\MyProjects\CosyStudio\data\cache\app.db')
    # 删除测试新增的 open_loops（不在备份中的 id）
    before_ids = [l["id"] for l in loops_before]
    conn.execute(
        "DELETE FROM webnovel_open_loops WHERE project_id = ? AND id NOT IN ({})".format(
            ','.join('?' * len(before_ids))), [project_id] + before_ids)
    # 恢复备份中各行原状态（status/resolved_chapter/urgency）
    for l in loops_before:
        conn.execute(
            """UPDATE webnovel_open_loops
               SET status=?, resolved_chapter=?, urgency=?, target_chapter=?, evidence=?
               WHERE id=?""",
            (l["status"], l["resolved_chapter"], l["urgency"],
             l["target_chapter"], l["evidence"], l["id"]))
    # 倒计时：删除新增，恢复备份行状态
    before_cd_ids = [c["id"] for c in cds_before]
    conn.execute(
        "DELETE FROM webnovel_timeline_countdown WHERE id NOT IN ({})".format(
            ','.join('?' * len(before_cd_ids))), before_cd_ids)
    for c in cds_before:
        conn.execute(
            """UPDATE webnovel_timeline_countdown
               SET event_name=?, start_countdown=?, current_status=?,
                   trigger_chapter=?, result=?
               WHERE id=?""",
            (c["event_name"], c["start_countdown"], c["current_status"],
             c["trigger_chapter"], c["result"], c["id"]))
    conn.commit()
    conn.close()


def db_state(project_id: int):
    conn = sqlite3.connect(r'C:\MyProjects\CosyStudio\data\cache\app.db')
    conn.row_factory = sqlite3.Row
    loops = [dict(r) for r in conn.execute(
        "SELECT * FROM webnovel_open_loops WHERE project_id = ?", (project_id,))]
    cds = [dict(r) for r in conn.execute(
        "SELECT * FROM webnovel_timeline_countdown")]
    conn.close()
    return loops, cds


async def main():
    project = get_webnovel_project_by_script(SCRIPT_ID)
    pid = project["id"]
    snap = snapshot(pid)
    contents = load_contents()
    print(f"[项目] project_id={pid}，备份 {len(snap[0])} 条open_loops / {len(snap[1])} 条countdowns")

    try:
        # ── 第一步：A 埋设章 ──
        print("\n========== 第一步：A 埋设章（验证提取） ==========")
        ex = CrossChapterEventProcessorExecutor(SCRIPT_ID, CHAPTER, 0)
        r1 = await ex.execute({"polished_content": contents["A"], "context_inventory": {}})
        print(f"[A] success={r1.success} summary={r1.step_summary}")
        loops_a, cds_a = db_state(pid)
        loops_before_ids = [l["id"] for l in snap[0]]
        cds_before_ids = [c["id"] for c in snap[1]]
        new_loops_a = [l for l in loops_a if l["id"] not in loops_before_ids]
        new_cds_a = [c for c in cds_a if c["id"] not in cds_before_ids]
        print(f"[A] 新增悬念 {len(new_loops_a)} 个：")
        for l in new_loops_a:
            print(f"    - [{l['tier']}] {l['content']}")
        print(f"[A] 新增倒计时 {len(new_cds_a)} 个：")
        for c in new_cds_a:
            print(f"    - {c['event_name']}（{c['start_countdown']}）status={c['current_status']}")
        assert len(new_loops_a) >= 2, "应识别出青铜匣+蒙面老者两个新悬念"
        assert len(new_cds_a) >= 2, "应识别出总攻+瘟疫两个新倒计时"
        print("[A] 提取断言通过 ✔")

        # ── 第二步：B 回收章 ──
        print("\n========== 第二步：B 回收章（验证回收/触发） ==========")
        ex2 = CrossChapterEventProcessorExecutor(SCRIPT_ID, CHAPTER, 0)
        r2 = await ex2.execute({"polished_content": contents["B"], "context_inventory": {}})
        print(f"[B] success={r2.success} summary={r2.step_summary}")
        loops_b, cds_b = db_state(pid)
        # 检查 A 埋的悬念是否被回收
        a_loop_ids = [l["id"] for l in new_loops_a]
        resolved_loops = [l for l in loops_b
                          if l["id"] in a_loop_ids and l["status"] == "resolved"]
        print(f"[B] A 埋悬念被回收 {len(resolved_loops)}/{len(a_loop_ids)}：")
        for l in resolved_loops:
            print(f"    - id={l['id']} {l['content'][:30]}... → resolved 第{l['resolved_chapter']}章")
        # 检查 A 埋的倒计时是否被触发/取消
        a_cd_ids = [c["id"] for c in new_cds_a]
        resolved_cds = [c for c in cds_b
                        if c["id"] in a_cd_ids and c["current_status"] != "未触发"]
        print(f"[B] A 埋倒计时结束 {len(resolved_cds)}/{len(a_cd_ids)}：")
        for c in resolved_cds:
            print(f"    - id={c['id']} {c['event_name']} → {c['current_status']} 第{c['trigger_chapter']}章")
        # B 中新增的"天罡旗"悬念
        loops_b_ids = [l["id"] for l in loops_b]
        new_in_b = [l for l in loops_b
                    if l["id"] not in loops_before_ids and l["id"] not in a_loop_ids]
        print(f"[B] 新增悬念（天罡旗应在此） {len(new_in_b)} 个：")
        for l in new_in_b:
            print(f"    - [{l['tier']}] {l['content']}")
        assert len(resolved_loops) >= 2, "A 埋的 2 个悬念都应被回收"
        assert len(resolved_cds) >= 2, "A 埋的 2 个倒计时都应被触发/取消"
        assert len(new_in_b) >= 1, "B 章应同时提取出天罡旗新悬念"
        print("[B] 回收/触发断言通过 ✔")

        print("\n========== 全部四类识别验证通过 ✔ ==========")
    finally:
        restore(pid, snap)
        print("\n[清理] 已恢复 project 93 原始数据")


if __name__ == "__main__":
    asyncio.run(main())
