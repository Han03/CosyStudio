import json
import re
import threading
from typing import Dict, Any, Optional

try:
    import json_repair
    HAS_JSON_REPAIR = True
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[llm_json_parser] json_repair 库已加载，版本: {getattr(json_repair, '__version__', 'unknown')}")
except ImportError:
    HAS_JSON_REPAIR = False


# 策略列表（名称、描述），与执行顺序一致
_PARSE_STRATEGIES = [
    ("direct", "直接解析/ json_repair 容错解析"),
    ("normalize_quotes", "统一中文引号到英文引号"),
    ("fix_missing_quotes", "修复缺失的引号(值缺前引号/键缺前引号/缺冒号)"),
    ("fix_string_end_key", "修复字符串结束后直接跟'key':"),
    ("fix_merged_keys", "修复被合并的键值对"),
    ("repair_json_quotes", "修复未转义的引号"),
    ("escape_newlines_in_strings", "转义字符串内的裸换行符"),
    ("fix_missing_colons", "修复缺失的冒号"),
    ("remove_trailing_commas", "移除尾逗号"),
    ("fix_missing_braces", "修复缺失的对象/数组闭合括号"),
    ("fix_missing_commas_in_arrays", "修复数组元素之间缺少逗号"),
    ("fix_missing_commas_in_objects", "修复对象属性之间缺少逗号"),
    ("extract_valid_json_fragment", "正则提取有效JSON片段"),
]

_log_lock = threading.Lock()
_log_pending: list = []
# 修复：日志必须"立即落盘"保留问题分析依据，不再按批量阈值攒缓存，避免创意约束包等步骤只产生1-2条日志时
# 一直攒在内存里不写入，导致服务重启/崩溃就丢失日志，或者用户短时间内看不到记录。
# （原阈值 8 条的初衷是避免高频抢锁，但日志量不大 + 独立 SQLite 连接 commit 足够快，立即落盘更重要）
_LOG_BATCH_SIZE = 1
_FORCE_FLUSH_AFTER_EVERY_ENQUEUE = True


def _flush_pending_logs():
    """将批量缓存的日志写入数据库（避免高频调用时反复抢锁）。"""
    global _log_pending
    with _log_lock:
        pending = _log_pending
        _log_pending = []
    if not pending:
        return
    try:
        from repositories.llm_call_log_repository import add_llm_call_log
    except Exception:
        return
    for kwargs in pending:
        try:
            add_llm_call_log(**kwargs)
        except Exception:
            pass


def _enqueue_log(kwargs: Dict[str, Any]):
    """入队一条日志，默认每条都立即 flush 写库（不攒缓存），保证问题分析日志可追溯。"""
    global _log_pending
    with _log_lock:
        _log_pending.append(kwargs)
        pending_count = len(_log_pending)
        should_flush = pending_count >= _LOG_BATCH_SIZE or _FORCE_FLUSH_AFTER_EVERY_ENQUEUE
    if should_flush:
        _flush_pending_logs()


def _build_log_kwargs(**explicit_kwargs) -> Dict[str, Any]:
    """合并显式参数与LLM上下文(如有）。
    显式参数优先级更高。上下文缺失时用显式参数补足。
    """
    merged: Dict[str, Any] = {}
    try:
        from core.llm_call_context import merge_llm_context
        merged = merge_llm_context(**explicit_kwargs)
    except Exception:
        merged = {k: v for k, v in explicit_kwargs.items() if v not in (None, "", 0)}
    # Merge explicit_kwargs 中 system_prompt / user_prompt，即便 merge_llm_context 已经合并了
    # 但要防止上下文里的 prompt 覆盖掉显式传的更完整的 prompt，
    # 所以把非空的显式 prompt 覆盖回 merged
    for key in ("system_prompt", "user_prompt", "request_id", "executor_name", "prompt_name",
                "model_name", "script_id", "project_id", "input_tokens", "output_tokens", "latency_ms"):
        v = explicit_kwargs.get(key)
        if v is not None and v != "" and v != 0:
            merged[key] = v
    return merged


def parse_llm_json(
    content: str,
    *,
    request_id: str = "",
    script_id: int = 0,
    project_id: int = 0,
    executor_name: str = "",
    prompt_name: str = "",
    model_name: str = "",
    system_prompt: str = "",
    user_prompt: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    enable_logging: bool = True,
) -> Optional[Dict[str, Any]]:
    """解析LLM输出的JSON内容，包含多种容错策略。

    解析结果（成功/失败、命中策略、原始内容）会异步写入 llm_call_logs 表，便于后续分析。
    默认会从当前LLM调用上下文中自动读取模型名、prompt、token、延迟等元数据，
    调用方也可通过参数显式传入（优先级更高）。
    """
    if not content:
        return None

    original_raw = content
    content = content.strip()

    # 移除 markdown 代码围栏
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]

    if content.endswith("```"):
        content = content[:-3]

    content = content.strip()

    # 提取最外层的 JSON 对象
    first_brace = content.find("{")
    last_brace = content.rfind("}")
    if first_brace != -1 and last_brace != -1:
        content = content[first_brace:last_brace + 1].strip()

    # 尝试解析
    def try_parse(text: str) -> Optional[Dict[str, Any]]:
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        if HAS_JSON_REPAIR:
            try:
                result = json_repair.loads(text)
                if isinstance(result, dict):
                    return result
            except Exception:
                pass

        return None

    strategies = [
        ("direct", lambda x: x),
        ("normalize_quotes", _normalize_quotes),
        ("fix_missing_quotes", _fix_missing_quotes),
        ("fix_string_end_key", _fix_string_end_key),
        ("fix_merged_keys", _fix_merged_keys),
        ("repair_json_quotes", _repair_json_quotes),
        ("escape_newlines_in_strings", _escape_newlines_in_strings),
        ("fix_missing_colons", _fix_missing_colons),
        ("remove_trailing_commas", _remove_trailing_commas),
        ("fix_missing_braces", _fix_missing_braces),
        ("fix_missing_commas_in_arrays", _fix_missing_commas_in_arrays),
        ("fix_missing_commas_in_objects", _fix_missing_commas_in_objects),
        ("extract_valid_json_fragment", _extract_valid_json_fragment),
    ]

    result = None
    success_strategy = ""
    strategies_tried = 0
    error_message = ""

    working = content
    for strategy_name, fix_fn in strategies:
        strategies_tried += 1
        try:
            candidate = fix_fn(working)
        except Exception as e:
            error_message = f"{strategy_name} 修复异常: {e}"
            candidate = working
        parsed = try_parse(candidate)
        if parsed:
            result = parsed
            success_strategy = strategy_name
            working = candidate
            break
        working = candidate

    if enable_logging:
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
                update_llm_call_log(log_id=existing_log_id, **log_kwargs)
            except Exception:
                pass
        else:
            _enqueue_log(log_kwargs)

    return result


def parse_llm_json_with_detail(
    content: str, **kwargs
) -> Dict[str, Any]:
    """解析LLM输出JSON并返回详细信息（结果+策略+失败原因）。"""
    result = parse_llm_json(content, **kwargs)
    # 策略命中情况可通过日志表查询，这里仅返回基础元数据
    return {
        "success": result is not None,
        "result": result,
    }


def flush_llm_call_logs():
    """强制写入所有缓存的LLM调用日志（服务关闭时调用）。"""
    _flush_pending_logs()


def _escape_newlines_in_strings(text: str) -> str:
    """转义 JSON 字符串值内的裸换行符。"""
    result = []
    in_string = False
    escape = False
    for char in text:
        if escape:
            result.append(char)
            escape = False
            continue
        if char == '\\':
            result.append(char)
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            result.append(char)
            continue
        if in_string and char == '\n':
            result.append('\\n')
            continue
        if in_string and char == '\r':
            result.append('\\r')
            continue
        result.append(char)
    return ''.join(result)


def _repair_json_quotes(text: str) -> str:
    """修复 JSON 字符串中未转义的引号（启发式修复）。"""
    result = []
    in_string = False
    i = 0
    n = len(text)
    
    while i < n:
        ch = text[i]
        
        if not in_string:
            if ch == '"':
                in_string = True
            result.append(ch)
            i += 1
            continue
        
        if ch == '\\' and i + 1 < n:
            result.append(ch)
            result.append(text[i + 1])
            i += 2
            continue
        
        if ch == '"':
            j = i + 1
            while j < n and text[j] in ' \t\n\r':
                j += 1
            
            if j >= n or text[j] in ',}]':
                in_string = False
                result.append(ch)
                i += 1
                continue
            
            if j < n and text[j] == ':':
                in_string = False
                result.append(ch)
                i += 1
                continue
            
            result.append('\\')
            result.append(ch)
            in_string = True
            i += 1
            continue
        
        result.append(ch)
        i += 1
    
    return ''.join(result)


def _fix_merged_keys(text: str) -> str:
    """修复被合并的键值对。"""
    result = []
    i = 0
    n = len(text)
    
    while i < n:
        if i + 1 < n and text[i] == '"' and text[i+1].isalpha():
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == '_'):
                j += 1
            
            k = j
            while k < n and text[k] in ' \t\n\r':
                k += 1
            
            if k < n and text[k] == ':':
                prev_pos = i - 1
                while prev_pos >= 0 and text[prev_pos] in ' \t\n\r':
                    prev_pos -= 1
                
                if prev_pos >= 0 and text[prev_pos] not in '{,:[':
                    result.append(',')
            
            result.append(text[i])
            i += 1
        else:
            result.append(text[i])
            i += 1
    
    return ''.join(result)


def _fix_string_end_key(text: str) -> str:
    """修复字符串结束后直接跟 "key": 的情况。"""
    pattern = r'(?<=[^\s{,:["])\s*"([\w_]+)":'
    text = re.sub(pattern, r', "\1":', text)
    text = text.replace('{,', '{')
    text = text.replace('[,', '[')
    return text


def _normalize_quotes(text: str) -> str:
    """统一中文引号到英文引号。"""
    text = text.replace('“', '"').replace('”', '"')
    text = text.replace('‘', "'").replace('’', "'")
    text = text.replace('「', '"').replace('」', '"')
    text = text.replace('【', '[').replace('】', ']')
    return text


def _fix_missing_quotes(text: str) -> str:
    """修复缺失的引号，覆盖三种常见LLM输出错误：
    1. 字符串值缺失前引号: "key":value  →  "key": "value"
    2. 键值间缺失冒号+值缺失前引号: "key "value  →  "key": "value"
    3. 键缺失前引号: , key":  →  , "key":
    采用状态机遍历，跟踪字符串边界与对象/数组上下文，避免误伤合法JSON。
    """
    result = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    ctx_stack = []  # True=对象, False=数组

    def is_obj():
        return bool(ctx_stack) and ctx_stack[-1]

    while i < n:
        ch = text[i]

        # 处理字符串内的转义字符
        if escape:
            result.append(ch)
            escape = False
            i += 1
            continue

        if in_string:
            if ch == '\\':
                result.append(ch)
                escape = True
                i += 1
                continue
            if ch == '"':
                in_string = False
                result.append(ch)
                i += 1
                # --- Fix 2: 键值间缺失冒号 ---
                if is_obj():
                    j = i
                    while j < n and text[j] in ' \t\n\r':
                        j += 1
                    if j < n:
                        next_ch = text[j]
                        # 合法后续: : , } ]   " 由 fix_missing_colons 处理
                        if next_ch not in ':,}]"':
                            # 判断下一token是key(缺逗号)还是value(缺冒号+前引号)
                            k = j
                            while k < n and (text[k].isalnum() or text[k] == '_'):
                                k += 1
                            m = k
                            while m < n and text[m] in ' \t':
                                m += 1
                            if m < n and text[m] == '"' and m + 1 < n and text[m + 1] == ':':
                                # 下一token是key → 缺逗号 + 键缺前引号
                                result.append(',')
                            else:
                                # 下一token是value → 缺冒号
                                result.append(':')
                            result.append(' ')
                            result.append('"')
                            in_string = True
                continue
            result.append(ch)
            i += 1
            continue

        # 不在字符串中
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue

        # --- Fix 1: 字符串值缺失前引号 ---
        if ch == ':':
            result.append(ch)
            i += 1
            # 保留空白
            while i < n and text[i] in ' \t\n\r':
                result.append(text[i])
                i += 1
            if i < n:
                next_ch = text[i]
                # 合法JSON值起始: " [ { 数字 - t(rue) f(alse) n(ull)
                if next_ch not in '"[{0123456789-tfn':
                    # 裸字符串值，补前引号
                    result.append('"')
                    # 读到结束符: " \n , } ]
                    while i < n and text[i] not in '"\n,}]':
                        result.append(text[i])
                        i += 1
                    # 去除尾部空白
                    while result and result[-1] in ' \t':
                        result.pop()
                    if i < n and text[i] == '"':
                        # 原始闭合引号存在，消费它
                        result.append('"')
                        i += 1
                    else:
                        # 无闭合引号，补一个
                        result.append('"')
            continue

        if ch == '{':
            ctx_stack.append(True)
            result.append(ch)
            i += 1
            # --- Fix 3: { 后键缺失前引号 ---
            j = i
            ws = []
            while j < n and text[j] in ' \t\n\r':
                ws.append(text[j])
                j += 1
            if j < n and text[j] not in '"}]' and (text[j].isalpha() or text[j] == '_'):
                k = j
                while k < n and (text[k].isalnum() or text[k] == '_'):
                    k += 1
                m = k
                while m < n and text[m] in ' \t':
                    m += 1
                if m < n and text[m] == '"' and m + 1 < n and text[m + 1] == ':':
                    result.extend(ws)
                    result.append('"')
                    in_string = True
                    i = j
                    continue
            result.extend(ws)
            i = j
            continue

        if ch == '[':
            ctx_stack.append(False)
            result.append(ch)
            i += 1
            continue

        if ch == '}':
            if ctx_stack:
                ctx_stack.pop()
            result.append(ch)
            i += 1
            continue

        if ch == ']':
            if ctx_stack:
                ctx_stack.pop()
            result.append(ch)
            i += 1
            continue

        # --- Fix 3 (续): , 后键缺失前引号 ---
        if ch == ',':
            result.append(ch)
            i += 1
            j = i
            ws = []
            while j < n and text[j] in ' \t\n\r':
                ws.append(text[j])
                j += 1
            if j < n and is_obj() and text[j] not in '"{}[]' and (text[j].isalpha() or text[j] == '_'):
                k = j
                while k < n and (text[k].isalnum() or text[k] == '_'):
                    k += 1
                m = k
                while m < n and text[m] in ' \t':
                    m += 1
                if m < n and text[m] == '"' and m + 1 < n and text[m + 1] == ':':
                    result.extend(ws)
                    result.append('"')
                    in_string = True
                    i = j
                    continue
            result.extend(ws)
            i = j
            continue

        result.append(ch)
        i += 1

    return ''.join(result)


def _fix_missing_colons(text: str) -> str:
    """修复缺失的冒号。"""
    text = re.sub(r'"(\w+)"\s*"', r'"\1": "', text)
    text = re.sub(r'"(\w+_[\w_]+)"\s*"', r'"\1": "', text)
    text = re.sub(r'"(\w+)\s+"', r'"\1": "', text)
    
    lines = text.split('\n')
    fixed_lines = []
    for line in lines:
        parts = re.findall(r'"([^"]*)"', line)
        if len(parts) >= 2:
            for i in range(len(parts) - 1):
                key_candidate = parts[i].strip()
                val_candidate = parts[i+1].strip()
                if key_candidate and key_candidate[0].isalpha() and val_candidate:
                    pattern = r'"' + re.escape(key_candidate + ' ') + r'"' + re.escape(val_candidate) + r'"'
                    replacement = '"' + key_candidate + '": "' + val_candidate + '"'
                    line = re.sub(pattern, replacement, line)
                    pattern2 = r'"' + re.escape(key_candidate) + r'"\s*"' + re.escape(val_candidate) + r'"'
                    line = re.sub(pattern2, replacement, line)
                    break
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)


def _remove_trailing_commas(text: str) -> str:
    """移除 JSON 中的多余尾逗号。"""
    text = re.sub(r',\s*(\]|\})', r'\1', text)
    return text


def _fix_missing_braces(text: str) -> str:
    """修复缺失的对象/数组闭合括号。"""
    lines = text.split('\n')
    result = []
    brace_stack = []
    in_string = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        if stripped.startswith('{') and i > 0 and result:
            prev_stripped = result[-1].strip()
            if prev_stripped and not prev_stripped.endswith(',') and not prev_stripped.endswith('{') and not prev_stripped.endswith('[') and not prev_stripped.endswith('}') and not prev_stripped.endswith(']'):
                result[-1] = result[-1].rstrip() + '},'
        
        processed_line = []
        for j, char in enumerate(line):
            if char == '"' and (j == 0 or line[j-1] != '\\'):
                in_string = not in_string
            
            processed_line.append(char)
            
            if not in_string:
                if char == '{':
                    brace_stack.append('{')
                elif char == '[':
                    brace_stack.append('[')
                elif char == '}':
                    if brace_stack and brace_stack[-1] == '{':
                        brace_stack.pop()
                elif char == ']':
                    if brace_stack and brace_stack[-1] == '[':
                        brace_stack.pop()
        
        result.append(''.join(processed_line))
    
    return '\n'.join(result)


def _fix_missing_commas_in_arrays(text: str) -> str:
    """修复数组元素之间缺少逗号的问题。"""
    result = []
    in_string = False
    in_array = False
    brace_level = 0
    i = 0
    n = len(text)
    
    while i < n:
        ch = text[i]
        
        if ch == '"' and (i == 0 or text[i-1] != '\\'):
            in_string = not in_string
            result.append(ch)
            i += 1
            continue
        
        if not in_string:
            if ch == '[':
                in_array = True
                brace_level = 0
                result.append(ch)
                i += 1
                continue
            
            if ch == ']':
                in_array = False
                result.append(ch)
                i += 1
                continue
            
            if in_array and ch == '{':
                brace_level += 1
                result.append(ch)
                i += 1
                continue
            
            if in_array and ch == '}':
                brace_level -= 1
                if brace_level == 0 and i + 1 < n and text[i+1] == '{':
                    result.append(ch)
                    result.append(',')
                    i += 1
                    continue
                result.append(ch)
                i += 1
                continue
        
        result.append(ch)
        i += 1
    
    return ''.join(result)


def _fix_missing_commas_in_objects(text: str) -> str:
    """修复对象属性之间缺少逗号的问题。"""
    result = []
    in_string = False
    after_value = False
    i = 0
    n = len(text)
    
    while i < n:
        ch = text[i]
        
        if ch == '"' and (i == 0 or text[i-1] != '\\'):
            in_string = not in_string
            if not in_string and after_value:
                j = i + 1
                while j < n and text[j] in ' \t\n\r':
                    j += 1
                if j < n and text[j] == '"':
                    result.append(ch)
                    result.append(',')
                    i += 1
                    after_value = False
                    continue
            result.append(ch)
            i += 1
            continue
        
        if not in_string:
            if ch == ':':
                after_value = False
            elif ch == '}' or ch == ']':
                after_value = False
            elif ch == ',':
                after_value = False
            elif after_value and ch not in ' \t\n\r':
                after_value = False
            elif ch == '[' or ch == '{':
                after_value = True
        
        result.append(ch)
        i += 1
    
    return ''.join(result)


def _extract_valid_json_fragment(text: str) -> str:
    """尝试提取有效的JSON片段。"""
    first_brace = text.find('{')
    if first_brace == -1:
        return text
    
    brace_count = 0
    i = first_brace
    n = len(text)
    
    while i < n:
        ch = text[i]
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0:
                return text[first_brace:i+1]
        i += 1
    
    return text[first_brace:]
