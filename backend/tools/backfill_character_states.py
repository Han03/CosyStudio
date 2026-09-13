# -*- coding: utf-8 -*-
"""回填角色状态表：从已写章节正文（1~N 章）提取章末角色状态。

用法:
  cd backend
  python -m tools.backfill_character_states --script 999912 [--max-chapter 7]

LLM 真调提取，每章 1 次；结果写入 webnovel_character_state。
"""
import argparse
import asyncio
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EXTRACT_SYSTEM = (
    "你是一位小说章节状态分析助手。阅读给定章节正文，提取各主要角色在本章"
    "【结束时】的状态快照，输出严格的 JSON。只提取正文中实际出场的角色，每角色一条。"
)

EXTRACT_USER = """【角色清单（含ID，仅限清单内角色）】
{char_list}

【章节正文】
{content}

请输出 JSON（不要输出其他内容）：
{{
  "states": [
    {{
      "character_id": 1,
      "character_name": "李承言",
      "location": "章末所在位置",
      "state_summary": "章末身体/处境状态（受伤/体力/得失/异常）",
      "emotion": "章末情绪",
      "possession": ["物品名1"],
      "knowledge": "本章新获得的信息与认知（无则空字符串）",
      "notes": "其他关键状态变化（无则空字符串）"
    }}
  ]
}}
要求：state_summary/emotion 用一句话概括；possession 只列本章结束时实际持有或确认的；knowledge 描述角色本章知晓了哪些新信息（决定知识边界）。"""


def load_content(script_id: int, chapter: int) -> str:
    p = os.path.join(
        r"C:\MyProjects\ai\CosyStudio\media\document\scripts",
        str(script_id), "chapters", f"{chapter}.txt",
    )
    if not os.path.exists(p):
        return ""
    with io.open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


async def extract_states(executor, script_id, project_id, chapter, content, char_list):
    prompt = EXTRACT_USER.format(char_list=char_list, content=content[:6000])
    try:
        result = await executor.execute_text_chat(
            prompt=prompt,
            system_prompt=EXTRACT_SYSTEM,
            max_tokens=2000,
            script_id=script_id,
            project_id=project_id,
            executor_name="character_state_backfill",
            prompt_name="character_state_extract",
        )
        raw = (result or {}).get("content", "") if result else ""
        if not raw:
            print(f"  第{chapter}章: LLM 无输出")
            return []
        # 容错提取 JSON
        text = raw.strip()
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < 0:
            print(f"  第{chapter}章: 无 JSON，原文: {raw[:120]}")
            return []
        obj = json.loads(text[start:end + 1])
        states = obj.get("states", [])
        if not isinstance(states, list):
            states = []
        return states
    except Exception as e:
        print(f"  第{chapter}章: 提取失败 {e}")
        return []


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", type=int, default=999912)
    parser.add_argument("--max-chapter", type=int, default=7)
    parser.add_argument("--start-chapter", type=int, default=1)
    args = parser.parse_args()

    from webnovel.repositories import (
        get_webnovel_project_by_script, get_character_cards_by_project,
        upsert_character_state,
    )
    from core.model_executor import get_model_executor

    project = get_webnovel_project_by_script(args.script)
    if not project:
        print("项目不存在")
        return
    project_id = project["id"]
    cards = get_character_cards_by_project(project_id)
    name2id = {c.get("name", ""): c.get("id") for c in cards if c.get("id")}
    char_list = "\n".join(
        f"{c.get('name','')}(id={c.get('id')})" for c in cards if c.get("name")
    )
    print(f"项目 {project_id} 角色卡 {len(cards)} 个")

    executor = get_model_executor()
    total_upserted = 0
    for ch in range(args.start_chapter, args.max_chapter + 1):
        content = load_content(args.script, ch)
        if not content:
            print(f"第{ch}章: 文件不存在，跳过")
            continue
        print(f"第{ch}章: 正文 {len(content)} 字，提取中...")
        states = await extract_states(
            executor, args.script, project_id, ch, content, char_list)
        for s in states:
            name = s.get("character_name", "")
            cid = s.get("character_id") or name2id.get(name)
            if not cid:
                print(f"    跳过未知角色: {name}")
                continue
            possession = s.get("possession") or []
            if isinstance(possession, list):
                possession = json.dumps(possession, ensure_ascii=False)
            upsert_character_state(
                project_id=project_id,
                character_id=cid,
                character_name=name,
                chapter_number=ch,
                location=s.get("location", ""),
                state_summary=s.get("state_summary", ""),
                emotion=s.get("emotion", ""),
                possession=possession,
                knowledge=s.get("knowledge", ""),
                notes=s.get("notes", ""),
            )
            total_upserted += 1
            print(f"    ✓ {name} | {s.get('state_summary','')[:40]}")
        print(f"  第{ch}章完成: {len(states)} 条")
    print(f"\n回填完成，共写入 {total_upserted} 条状态记录")


if __name__ == "__main__":
    asyncio.run(main())
