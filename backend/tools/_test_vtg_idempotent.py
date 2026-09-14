# -*- coding: utf-8 -*-
"""幂等逻辑测试：非卷首章跳过 / 卷首章已有主记录跳过（不调 LLM）"""
import sys, os, asyncio
sys.path.insert(0, r"C:\MyProjects\CosyStudio\backend")
os.chdir(r"C:\MyProjects\CosyStudio\backend")

from webnovel.pipeline.executors.volume_timeline_generator_executor import VolumeTimelineGeneratorExecutor


async def run(script_id, chapter_index):
    ex = VolumeTimelineGeneratorExecutor(script_id, chapter_index, 0)
    r = await ex.execute({})
    print(f"chapter={chapter_index}: success={r.success} summary={r.step_summary} data={r.output_data}")
    return r


async def main():
    # 第 4 章：非卷首章 → 跳过
    await run(999913, 4)
    # 第 1 章：卷首章但已有主记录 → 跳过（幂等）
    await run(999913, 1)


asyncio.run(main())
