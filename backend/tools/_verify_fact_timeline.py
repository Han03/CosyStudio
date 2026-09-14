# -*- coding: utf-8 -*-
"""验证 fact_record 第 7 块（章节时间轴）：prompt 渲染 / 解析 / 前章时间轴构造 / 落库幂等"""
import sys, os, json, asyncio, py_compile
sys.path.insert(0, r"C:\MyProjects\CosyStudio\backend")
os.chdir(r"C:\MyProjects\CosyStudio\backend")

py_compile.compile(r"webnovel\pipeline\executors\fact_recorder_executor.py", doraise=True)
print("[OK] 编译通过")

from webnovel.pipeline.executors.fact_recorder_executor import FactRecorderExecutor
from webnovel.repositories import get_timeline_chapters, get_timelines_by_project

SCRIPT_ID, CHAPTER = 999913, 50  # 用第 50 章（已有前章时间轴数据）验证
ex = FactRecorderExecutor(SCRIPT_ID, CHAPTER, 0)

# 1. prompt 渲染（真实输入）
project = __import__("webnovel.repositories", fromlist=["get_webnovel_project_by_script"]).get_webnovel_project_by_script(SCRIPT_ID)
project_id = project["id"]
pd = ex._load_prompt("fact_record")
prev = ex._build_prev_timeline_text(project_id, CHAPTER)
assert prev and "第49章" in prev, f"前章时间轴构造异常: {prev}"
print("[OK] 前章时间轴文本:\n", prev)
prompt = pd["user_prompt"].format(
    chapter_content="（示例章节内容）崇祯十年九月二十二……",
    world_settings=json.dumps(["明朝"], ensure_ascii=False),
    characters=json.dumps(["李威"], ensure_ascii=False),
    prev_timeline=prev,
)
assert "【章节时间轴 chapter_timeline】" in prompt and "前一章时间轴" in prompt
assert "{{" not in prompt.replace("{{", ""), "模板占位未替换"
print("[OK] prompt 渲染包含第 7 块，长度:", len(prompt))

# 2. 解析（模拟 LLM 输出）
sample = json.dumps({
    "item_changes": [],
    "character_updates": [],
    "cool_points": [],
    "hook": {},
    "character_states": [],
    "world_settings": [],
    "chapter_timeline": {
        "time_anchor": "崇祯十年九月二十二 下午未时",
        "chapter_duration": "8小时",
        "interval_from_prev": "跨夜(12小时)",
        "countdown_status": "初霜冻害(持续中)",
        "notes": "原文明确时间",
    },
}, ensure_ascii=False)
r = ex._parse_all(sample, SCRIPT_ID, project_id)
assert len(r) == 7, "解析应返回 7 元组"
ct = r[6]
assert ct.get("time_anchor") == "崇祯十年九月二十二 下午未时", ct
print("[OK] 解析第 7 块:", ct)

# 3. 落库（真实 upsert，第 50 章已有规划生成的记录 → 更新为原文分析结果）
tl = get_timelines_by_project(project_id)[0]
before = next(c for c in get_timeline_chapters(tl["id"]) if c["chapter_number"] == CHAPTER)
print("[OK] 落库前 ch50:", before.get("time_anchor"), "|", before.get("interval_from_prev"))

async def main():
    await ex._save_chapter_timeline(project_id, CHAPTER, ct)
asyncio.run(main())

after = next(c for c in get_timeline_chapters(tl["id"]) if c["chapter_number"] == CHAPTER)
print("[OK] 落库后 ch50:", after.get("time_anchor"), "|", after.get("interval_from_prev"), "| notes:", after.get("notes"))
assert after["time_anchor"] == "崇祯十年九月二十二 下午未时"
assert after["chapter_duration"] == "8小时"
print("[OK] 落库验证通过（原文分析结果已写入）")

# 4. 空/无前章场景
empty = ex._parse_all("{}", SCRIPT_ID, project_id)[6]
assert empty == {}
print("[OK] 空输出解析为 {}")
print(ex._build_prev_timeline_text(project_id, 1))  # 第 1 章 → 起始章提示
