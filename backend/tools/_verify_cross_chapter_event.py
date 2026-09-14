# 验证：跨章节事件处理器实测（第 4 章真实内容）
# 用法: python tools/_verify_cross_chapter_event.py
import asyncio
import sys

sys.path.insert(0, '.')

from webnovel.pipeline.executors.cross_chapter_event_processor_executor import (
    CrossChapterEventProcessorExecutor,
)
from webnovel.repositories import (
    get_webnovel_project_by_script,
    get_open_loops_by_project,
    get_timelines_by_project,
    get_timeline_countdowns,
)
from services.script_service import ScriptService

SCRIPT_ID = 999913
CHAPTER = 4


async def main():
    project = get_webnovel_project_by_script(SCRIPT_ID)
    pid = project["id"]
    print(f"[项目] project_id={pid}")

    # 前状态
    loops_before = get_open_loops_by_project(pid) or []
    active_before = [l for l in loops_before if l.get("status") == "active"]
    timelines = get_timelines_by_project(pid)
    tl = timelines[0] if timelines else None
    cds_before = get_timeline_countdowns(tl["id"]) if tl else []
    print(f"[前状态] open_loops={len(loops_before)} active={len(active_before)} "
          f"countdowns={len(cds_before)} timeline_id={tl and tl['id']}")

    # 原文
    svc = ScriptService()
    content_data = svc.get_chapter_content(SCRIPT_ID, CHAPTER)
    content = content_data.get("content", "") if content_data else ""
    print(f"[原文] 长度={len(content)}")

    ex = CrossChapterEventProcessorExecutor(SCRIPT_ID, CHAPTER, 0)
    result = await ex.execute({
        "polished_content": content,
        "context_inventory": {},
    })
    print(f"[结果] success={result.success}")
    print(f"[summary] {result.step_summary}")
    if not result.success:
        print(f"[错误] {result.error_message}")
        return

    # 后状态
    loops_after = get_open_loops_by_project(pid) or []
    active_after = [l for l in loops_after if l.get("status") == "active"]
    cds_after = get_timeline_countdowns(tl["id"]) if tl else []
    print(f"[后状态] open_loops={len(loops_after)} active={len(active_after)} "
          f"countdowns={len(cds_after)}")
    print(f"[新增open_loops]")
    for l in loops_after:
        if l.get("id") not in [b.get("id") for b in loops_before]:
            print(f"  id={l['id']} [{l.get('tier')}] {l.get('content', '')[:60]} "
                  f"(第{l.get('planted_chapter')}章)")
    print(f"[新增countdowns]")
    for c in cds_after:
        if c.get("id") not in [b.get("id") for b in cds_before]:
            print(f"  id={c['id']} {c.get('event_name')}（{c.get('start_countdown')}）"
                  f" status={c.get('current_status')}")
    print(f"[活跃悬念状态]")
    for l in active_after:
        print(f"  id={l['id']} {l.get('content', '')[:50]} status={l.get('status')}")
    print(f"[倒计时状态]")
    for c in cds_after:
        print(f"  id={c['id']} {c.get('event_name')} status={c.get('current_status')} "
              f"trigger_chapter={c.get('trigger_chapter')}")


if __name__ == "__main__":
    asyncio.run(main())
