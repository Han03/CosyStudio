# -*- coding: utf-8 -*-
"""端到端验证：execute_text_chat 日志的 parse_success 探测 + token 记录 + parse_llm_json 回填。"""
import asyncio
import sqlite3

DB = r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db"


def last_log(prompt_name):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, parse_success, success_strategy, input_tokens, output_tokens, latency_ms "
        "FROM llm_call_logs WHERE prompt_name=? ORDER BY id DESC LIMIT 1", (prompt_name,))
    r = cur.fetchone()
    conn.close()
    return r


async def main():
    from core.model_executor import get_model_executor
    from utils.llm_json_parser import parse_llm_json
    ex = get_model_executor()

    # 场景A：未走 parse_llm_json（类似草稿/审查自定义解析）→ parse_success 应由探测回填
    r = await ex.execute_text_chat(
        '只输出JSON：{"content": "你好"}',
        system_prompt="测试", max_tokens=100,
        script_id=0, project_id=0,
        executor_name="__verify_probe", prompt_name="__v_probe",
    )
    row = last_log("__v_probe")
    print(f"[A 探测] parse_success={row[1]} strategy={row[2]!r} tok={row[3]}/{row[4]} lat={row[5]}")
    assert row[1] == 1, "未走 parse 的 JSON 输出，探测应标记 parse_success=1"
    assert (row[3] or 0) > 0, "token 应已记录"

    # 场景B：走 parse_llm_json → 桥接 UPDATE 覆盖（更精确 + success_strategy）
    r2 = await ex.execute_text_chat(
        '只输出JSON：{"ok": true, "list": [1,2,3]}',
        system_prompt="测试", max_tokens=100,
        script_id=0, project_id=0,
        executor_name="__verify_parse", prompt_name="__v_parse",
    )
    parsed = parse_llm_json(
        r2.get("content", ""),
        script_id=0, project_id=0,
        executor_name="__verify_parse", prompt_name="__v_parse",
    )
    row2 = last_log("__v_parse")
    print(f"[B 回填] parse_success={row2[1]} strategy={row2[2]!r} tok={row2[3]}/{row2[4]} parsed_ok={parsed is not None}")
    assert row2[1] == 1 and parsed is not None, "parse_llm_json 应回填 parse_success=1"

    print("✓ 端到端验证通过")


asyncio.run(main())
