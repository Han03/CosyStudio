# -*- coding: utf-8 -*-
"""全流程诊断运行器：真实跑「智能创作 + 应用结果」，记录每一步到独立文件夹。

用法（conda cosy_chat 环境，backend 目录下）：
    python tools/pipeline_diag/runner.py --script 999913 --chapter 2 --tag ch2_first
    python tools/pipeline_diag/runner.py --script 999913 --chapter 2 --no-polish
    python tools/pipeline_diag/runner.py --script 999913 --chapter 2 --dry-init   # 仅初始化不跑

产物：
    backend/data/pipeline_diag_runs/<script_id>/<chapter>/<tag>_<ts>/
      meta.json / llm_calls.jsonl / steps.jsonl / db_writes.jsonl / events.jsonl / summary.json
"""

import argparse
import asyncio
import io
import os
import sys
import time
from typing import Any, Dict

# 确保 backend 根目录可导入（独立脚本入口时生效）
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

# stdout 强制 UTF-8（Windows GBK 控制台会炸中文）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from tools.pipeline_diag.recorder import PipelineDiagRecorder
from tools.pipeline_diag.instrument import install, uninstall


async def _poll_task(script_id: int, task_id: int, label: str,
                     poll_interval: float = 5.0, timeout_s: float = 7200):
    """轮询 writing_task 直到 completed/failed/cancelled。"""
    from repositories import get_writing_task

    started = time.time()
    last_status = ""
    while time.time() - started < timeout_s:
        task = get_writing_task(script_id, task_id)
        if not task:
            raise RuntimeError(f"{label} task_id={task_id} 不存在")
        status = task.get("status", "")
        if status != last_status:
            print(f"  [{label}] status={status} progress={task.get('progress')} "
                  f"msg={str(task.get('progress_message', ''))[:80]}")
            last_status = status
        if status in ("completed", "failed", "cancelled"):
            return task
        await asyncio.sleep(poll_interval)
    raise TimeoutError(f"{label} task_id={task_id} 超时（>{int(timeout_s)}s）")


async def run_full(script_id: int, chapter_index: int, tag: str,
                   enable_polish: bool = True, poll_interval: float = 5.0,
                   timeout_s: float = 7200) -> Dict[str, Any]:
    """跑完整「智能创作 + 应用结果」，返回 summary。"""
    recorder = PipelineDiagRecorder(script_id, chapter_index, tag)
    print(f"[diag] 输出目录: {recorder.dir}")
    install(recorder)
    try:
        from webnovel.services.webnovel_service import WebnovelService
        service = WebnovelService()

        # ── 阶段 1：智能创作 ──
        recorder.mark_stage("writing")
        print(f"[diag] 开始智能创作: script={script_id} chapter={chapter_index} "
              f"enable_polish={enable_polish}")
        r = await service.continue_chapter(script_id, chapter_index, enable_polish=enable_polish)
        if not r.get("success"):
            raise RuntimeError(f"创作任务创建失败: {r.get('error')}")
        task_id = r["task_id"]
        print(f"[diag] 创作任务已创建 task_id={task_id}")
        task = await _poll_task(script_id, task_id, "writing", poll_interval, timeout_s)
        if task.get("status") != "completed":
            raise RuntimeError(f"创作任务未完成: {task.get('status')} "
                               f"{str(task.get('error_message', ''))[:200]}")

        # ── 阶段 2：应用结果 ──
        recorder.mark_stage("apply")
        print(f"[diag] 开始应用结果: source_task_id={task_id}")
        a = await service.apply_continue_result_as_task(script_id, chapter_index, task_id)
        if not a.get("success"):
            raise RuntimeError(f"应用任务创建失败: {a.get('error')}")
        apply_task_id = a["apply_task_id"]
        print(f"[diag] 应用任务已创建 apply_task_id={apply_task_id}")
        atask = await _poll_task(script_id, apply_task_id, "apply", poll_interval, timeout_s)
        if atask.get("status") != "completed":
            raise RuntimeError(f"应用任务未完成: {atask.get('status')} "
                               f"{str(atask.get('error_message', ''))[:200]}")

        print("[diag] 全流程完成")
    finally:
        uninstall()
        summary = recorder.finalize({
            "enable_polish": enable_polish,
            "pipeline": "continue_chapter -> apply_continue_result_as_task",
        })
    return summary


def main():
    ap = argparse.ArgumentParser(description="CosyStudio 全流程诊断运行器")
    ap.add_argument("--script", type=int, required=True, help="script_id")
    ap.add_argument("--chapter", type=int, required=True, help="章节目录索引")
    ap.add_argument("--tag", default="diag", help="运行标签（输出目录名）")
    ap.add_argument("--no-polish", action="store_true", help="关闭润色节点")
    ap.add_argument("--poll-interval", type=float, default=5.0)
    ap.add_argument("--timeout", type=float, default=7200.0, help="总超时秒数")
    ap.add_argument("--dry-init", action="store_true", help="仅初始化记录器并退出（自检用）")
    args = ap.parse_args()

    if args.dry_init:
        rec = PipelineDiagRecorder(args.script, args.chapter, args.tag)
        print(f"[dry] 输出目录: {rec.dir}")
        rec.finalize({"dry_init": True})
        print("[dry] 自检完成")
        return

    summary = asyncio.run(run_full(
        args.script, args.chapter, args.tag,
        enable_polish=not args.no_polish,
        poll_interval=args.poll_interval,
        timeout_s=args.timeout,
    ))

    stats = summary["stats"]
    print("\n==== 全流程诊断汇总 ====")
    print(f"  运行目录: {summary['meta']['run_dir']}")
    print(f"  总耗时  : {summary['meta']['elapsed_s']}s")
    print("  LLM 调用（executor|prompt → 次数/输入tok/输出tok/延迟ms）:")
    for k, v in sorted(stats["llm_by_executor"].items(), key=lambda kv: kv[1]["count"], reverse=True):
        print(f"    {k}: {v['count']}次 in={v['in_tok']} out={v['out_tok']} "
              f"latency={v['latency_ms']}ms errors={v['errors']}")
    print("  DB 写入（表 → 次数）:")
    for k, v in sorted(stats["db_by_table"].items(), key=lambda kv: kv[1]["count"], reverse=True):
        print(f"    {k}: {v['count']}")
    print(f"  步骤: {len(stats['steps'])} 个，失败 {sum(1 for s in stats['steps'] if not s['success'])} 个")
    for s in stats["steps"]:
        mark = "OK " if s["success"] else "FAIL"
        print(f"    [{mark}] {s['step']}: {s['elapsed_s']}s "
              f"llm={len(s['llm_seqs'])} db={len(s['db_seqs'])} {s.get('summary', '')[:60]}")


if __name__ == "__main__":
    main()
