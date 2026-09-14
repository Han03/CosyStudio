# -*- coding: utf-8 -*-
"""实测 execute_text_chat 两条路径的 token 返回（小 prompt，成本极低）。"""
import asyncio


async def main():
    from core.model_executor import get_model_executor
    ex = get_model_executor()

    for en, pn in (("context_analyzer", "__tok_test_ctx"),
                   ("draft_reviewer_score", "__tok_test_review"),
                   ("draft_generator", "__tok_test_draft")):
        try:
            r = await ex.execute_text_chat(
                "用中文回答：你是什么模型？只回答一行。",
                system_prompt="测试",
                max_tokens=50,
                script_id=0, project_id=0,
                executor_name=en, prompt_name=pn,
            )
            print(f"[{en}] model={r.get('model_name')} in={r.get('input_tokens')} out={r.get('output_tokens')} lat={r.get('latency_ms')} content={str(r.get('content'))[:60]!r}")
        except Exception as e:
            print(f"[{en}] ERROR {type(e).__name__}: {e}")


asyncio.run(main())
