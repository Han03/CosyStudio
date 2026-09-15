# -*- coding: utf-8 -*-
"""CSV 创作知识重索引工具（修复题材错位后对现有项目重建）。

用法（在 backend 目录下）：
    python tools/reindex_csv_knowledge.py --script 999916
    python tools/reindex_csv_knowledge.py --project 97
    python tools/reindex_csv_knowledge.py --all

force=True：先清空该项目 csv_* 类型 chunk 再重建（source_key 幂等防重复）。
执行后打印各 csv_* 类型 chunk 数量与 has_csv_knowledge 状态供验证。
"""

import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from webnovel.repositories import get_webnovel_project, get_webnovel_project_by_script
from webnovel.services.webnovel_service import WebnovelService
from services.vector_store import get_rag_service


async def _reindex_one(svc: WebnovelService, project_id: int) -> None:
    from webnovel.repositories import get_webnovel_project
    project = get_webnovel_project(project_id)
    if not project:
        print(f"[SKIP] 项目 {project_id} 不存在")
        return
    print(f"[开始] project {project_id} ({project.get('title')}, genre={project.get('genre')})")
    await svc._index_csv_knowledge(project_id, force=True)
    rag = get_rag_service()
    print(f"[完成] project {project_id} has_csv_knowledge={rag.has_csv_knowledge(project_id)}")
    for ct in (
        "csv_plot", "csv_pacing", "csv_verdict", "csv_scene", "csv_writing",
        "csv_naming", "csv_character_knowledge",
        "csv_golden_finger_knowledge", "csv_genre_tone",
    ):
        n = len(rag.get_chunks(project_id, ct))
        if n:
            print(f"   {ct}: {n}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="CSV 创作知识重索引")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--script", type=int, help="剧本 script_id")
    group.add_argument("--project", type=int, help="webnovel project_id")
    group.add_argument("--all", action="store_true", help="全部项目重索引")
    args = parser.parse_args()

    svc = WebnovelService()
    if args.script:
        project = get_webnovel_project_by_script(args.script)
        if not project:
            print(f"[SKIP] 剧本 {args.script} 无关联 webnovel 项目")
            return
        await _reindex_one(svc, project["id"])
    elif args.project:
        await _reindex_one(svc, args.project)
    else:
        from webnovel.repositories import get_all_webnovel_projects
        projects = get_all_webnovel_projects() or []
        if not projects:
            print("[SKIP] 无任何 webnovel 项目")
            return
        for p in projects:
            await _reindex_one(svc, p["id"])


if __name__ == "__main__":
    asyncio.run(main())
