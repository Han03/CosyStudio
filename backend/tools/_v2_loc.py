# -*- coding: utf-8 -*-
"""定位 B 场景 token=0：INSERT 时即 0 还是被 UPDATE 覆盖。"""
import asyncio
import sqlite3

DB = r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db"


def get_rows(prompt_name):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, parse_success, success_strategy, input_tokens, output_tokens, latency_ms, created_at "
        "FROM llm_call_logs WHERE prompt_name=? ORDER BY id DESC LIMIT 3", (prompt_name,))
    rows = cur.fetchall()
    conn.close()
    return rows


async def main():
    from core.model_executor import get_model_executor
    from utils.llm_json_parser import parse_llm_json
    ex = get_model_executor()

    r = await ex.execute_text_chat(
        '只输出JSON：{"ok": 1}',
        system_prompt="t", max_tokens=60,
        script_id=0, project_id=0,
        executor_name="__v2", prompt_name="__v2_parse",
    )
    print("execute_text_chat 返回:", {k: r.get(k) for k in ("model_name", "input_tokens", "output_tokens", "latency_ms")})
    print("INSERT 后日志:", get_rows("__v2_parse"))

    parsed = parse_llm_json(
        r.get("content", ""),
        script_id=0, project_id=0,
        executor_name="__v2", prompt_name="__v2_parse",
    )
    print("parse 结果:", parsed)
    print("UPDATE 后日志:", get_rows("__v2_parse"))


asyncio.run(main())
