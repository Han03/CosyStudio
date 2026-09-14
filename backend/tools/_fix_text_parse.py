# -*- coding: utf-8 -*-
"""修复纯文本节点日志误报：parse_llm_json 加 expect_json 参数。

根因：去 JSON 包装后，草稿/润色/草稿修订输出纯文本正文，
但 executor 仍走 parse_llm_json（12 种 JSON 策略全失败 →
strategies_tried=12 / parse_success=0 / parsed_output 空），
被误读为"输出为空"。功能正常（executor 有原文兜底），仅日志语义错误。

修复：expect_json=False 时直接以原文为产物，日志记录 direct_text 成功。
"""
p = r"C:\MyProjects\CosyStudio\backend\utils\llm_json_parser.py"
with open(p, encoding="utf-8") as f:
    t = f.read()

# 1. 签名加参数
old1 = '''    latency_ms: int = 0,
    enable_logging: bool = True,
) -> Optional[Dict[str, Any]]:'''
new1 = '''    latency_ms: int = 0,
    enable_logging: bool = True,
    expect_json: bool = True,
) -> Optional[Dict[str, Any]]:'''
if old1 not in t:
    raise SystemExit("签名未找到")
t = t.replace(old1, new1, 1)

# 2. 开头加纯文本分支（content 非空检查之后）
old2 = '''    if not content:
        return None

    original_raw = content
    content = content.strip()

    # 移除 markdown 代码围栏'''
new2 = '''    if not content:
        return None

    original_raw = content
    content = content.strip()

    if not expect_json:
        # 纯文本节点（草稿/润色/草稿修订）：正文即产物，不做 JSON 策略解析。
        # 避免 12 种 JSON 策略全失败导致 strategies_tried=12 / parse_success=0，
        # 日志被误读为"输出为空"。
        text_result = {"content": content}
        if enable_logging:
            _log_kwargs = _build_log_kwargs(
                request_id=request_id,
                script_id=script_id,
                project_id=project_id,
                executor_name=executor_name,
                prompt_name=prompt_name,
                model_name=model_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
            )
            _log_kwargs["raw_output"] = original_raw
            _log_kwargs["parsed_output"] = text_result
            _log_kwargs["parse_success"] = True
            _log_kwargs["success_strategy"] = "direct_text"
            _log_kwargs["strategies_tried"] = 1
            _log_kwargs["error_message"] = ""
            _write_parse_log(_log_kwargs)
        return text_result

    # 移除 markdown 代码围栏'''
if old2 not in t:
    raise SystemExit("入口未找到")
t = t.replace(old2, new2, 1)

# 3. 原日志写入段抽成公共函数 _write_parse_log，供两处复用
old3 = '''    if enable_logging:
        log_kwargs = _build_log_kwargs(
            request_id=request_id,
            script_id=script_id,
            project_id=project_id,
            executor_name=executor_name,
            prompt_name=prompt_name,
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
        log_kwargs["raw_output"] = original_raw
        log_kwargs["parsed_output"] = result
        log_kwargs["parse_success"] = result is not None
        log_kwargs["success_strategy"] = success_strategy
        log_kwargs["strategies_tried"] = strategies_tried
        log_kwargs["error_message"] = error_message

        # 🔴 如果桥接中有 log_id（由 model_executor 首次 INSERT 产生），
        #    则执行 UPDATE 补充解析结果，避免重复插入两条日志。
        try:
            from core.llm_call_context import consume_log_bridge
            existing_log_id = consume_log_bridge()
        except Exception:
            existing_log_id = 0
        # 同时清理 merge 进来的 log_id 字段，避免传入 repository 报错
        log_kwargs.pop("log_id", None)

        if existing_log_id > 0:
            try:
                from repositories.llm_call_log_repository import update_llm_call_log
                # 🔴 update_llm_call_log 仅接受固定参数集，必须先过滤掉 log_kwargs 中的
                #    元数据键（request_id/executor_name/system_prompt 等），否则 TypeError 会导致
                #    解析结果回写失败、日志里 parse_success 永远为假 0。
                # token/latency 由 execute_text_chat 统一测量并 INSERT，parse 阶段绝不回写：
                # update_llm_call_log 无条件覆盖全部列（缺省参数=0），若把这三个键放进来，
                # 会把 INSERT 时的真实 token/latency 覆盖成 0（历史 ctx_analysis 等全 0 的根因）。
                _allowed_update_keys = (
                    "raw_output", "parsed_output", "parse_success", "success_strategy",
                    "strategies_tried", "error_message",
                )
                update_kwargs = {k: v for k, v in log_kwargs.items() if k in _allowed_update_keys}
                update_llm_call_log(log_id=existing_log_id, **update_kwargs)
            except Exception as _upd_ex:
                try:
                    from utils.logger import log_manager
                    log_manager.get_logger("llm_call_log").error(
                        f"[LLM_LOG_UPDATE_SKIP] {type(_upd_ex).__name__}: {_upd_ex}"
                    )
                except Exception:
                    pass
        else:
            # 无桥接 log_id：本次解析并非来自 execute_text_chat 的真实 LLM 调用
            # （探针/测试/内部直接喂文本解析），不落 llm_call_logs，避免产生
            # user_prompt/system_prompt 为空的假日志污染日志库、干扰问题分析。
            # 真实 LLM 调用必经 execute_text_chat（统一入口必落库），解析只负责回写。
            try:
                from utils.logger import log_manager
                log_manager.get_logger("llm_call_log").warning(
                    f"[PARSE_NO_LLM_BRIDGE] 跳过落库（非LLM调用解析）: "
                    f"executor={executor_name or '-'} prompt={prompt_name or '-'} "
                    f"raw_len={len(original_raw or '')}"
                )
            except Exception:
                pass

    return result'''
new3 = '''    if enable_logging:
        log_kwargs = _build_log_kwargs(
            request_id=request_id,
            script_id=script_id,
            project_id=project_id,
            executor_name=executor_name,
            prompt_name=prompt_name,
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
        log_kwargs["raw_output"] = original_raw
        log_kwargs["parsed_output"] = result
        log_kwargs["parse_success"] = result is not None
        log_kwargs["success_strategy"] = success_strategy
        log_kwargs["strategies_tried"] = strategies_tried
        log_kwargs["error_message"] = error_message
        _write_parse_log(log_kwargs)

    return result


def _write_parse_log(log_kwargs: dict) -> None:
    """将解析结果回写 llm_call_logs（复用 execute_text_chat 的 INSERT 行）。"""
    # 🔴 如果桥接中有 log_id（由 model_executor 首次 INSERT 产生），
    #    则执行 UPDATE 补充解析结果，避免重复插入两条日志。
    try:
        from core.llm_call_context import consume_log_bridge
        existing_log_id = consume_log_bridge()
    except Exception:
        existing_log_id = 0
    # 同时清理 merge 进来的 log_id 字段，避免传入 repository 报错
    log_kwargs.pop("log_id", None)

    if existing_log_id > 0:
        try:
            from repositories.llm_call_log_repository import update_llm_call_log
            # 🔴 update_llm_call_log 仅接受固定参数集，必须先过滤掉 log_kwargs 中的
            #    元数据键（request_id/executor_name/system_prompt 等），否则 TypeError 会导致
            #    解析结果回写失败、日志里 parse_success 永远为假 0。
            # token/latency 由 execute_text_chat 统一测量并 INSERT，parse 阶段绝不回写：
            # update_llm_call_log 无条件覆盖全部列（缺省参数=0），若把这三个键放进来，
            # 会把 INSERT 时的真实 token/latency 覆盖成 0（历史 ctx_analysis 等全 0 的根因）。
            _allowed_update_keys = (
                "raw_output", "parsed_output", "parse_success", "success_strategy",
                "strategies_tried", "error_message",
            )
            update_kwargs = {k: v for k, v in log_kwargs.items() if k in _allowed_update_keys}
            update_llm_call_log(log_id=existing_log_id, **update_kwargs)
        except Exception as _upd_ex:
            try:
                from utils.logger import log_manager
                log_manager.get_logger("llm_call_log").error(
                    f"[LLM_LOG_UPDATE_SKIP] {type(_upd_ex).__name__}: {_upd_ex}"
                )
            except Exception:
                pass
    else:
        # 无桥接 log_id：本次解析并非来自 execute_text_chat 的真实 LLM 调用
        # （探针/测试/内部直接喂文本解析），不落 llm_call_logs，避免产生
        # user_prompt/system_prompt 为空的假日志污染日志库、干扰问题分析。
        # 真实 LLM 调用必经 execute_text_chat（统一入口必落库），解析只负责回写。
        try:
            from utils.logger import log_manager
            log_manager.get_logger("llm_call_log").warning(
                f"[PARSE_NO_LLM_BRIDGE] 跳过落库（非LLM调用解析）: "
                f"executor={log_kwargs.get('executor_name', '-')} prompt={log_kwargs.get('prompt_name', '-')} "
                f"raw_len={len(str(log_kwargs.get('raw_output', '') or ''))}"
            )
        except Exception:
            pass'''
if old3 not in t:
    raise SystemExit("日志段未找到")
t = t.replace(old3, new3, 1)

with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(t)
import py_compile
py_compile.compile(p, doraise=True)
print("[OK] llm_json_parser: expect_json 参数 + _write_parse_log 抽取完成")
