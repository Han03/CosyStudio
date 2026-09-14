# -*- coding: utf-8 -*-
"""重写 update_llm_call_log 为动态字段更新（缺省键不覆盖，避免 token/latency 被清 0）。"""
import re

p = r"C:\MyProjects\CosyStudio\backend\repositories\llm_call_log_repository.py"
with open(p, encoding="utf-8") as f:
    content = f.read()

old_start = "def update_llm_call_log(\n"
idx = content.find(old_start)
assert idx != -1, "def not found"
# 找函数体结束：下一个顶格 def 或文件其他标记
next_def = content.find("\n\ndef ", idx + 10)
if next_def == -1:
    next_def = len(content)
old_block = content[idx:next_def]

new_block = '''def update_llm_call_log(log_id: int, **fields) -> bool:
    """更新已有的LLM调用日志（用于 parse_llm_json 补充解析结果，避免重复插入）。

    典型场景：model_executor 的 finally 块先 INSERT 一条包含 raw_output 的日志并返回 log_id，
    随后 parse_llm_json 解析完成后通过本函数 UPDATE 同一条记录，补充 parsed_output / 解析策略等字段。

    🔴 仅更新显式传入的字段（kwargs 语义）：缺省的键不写入 SQL。
       旧实现无条件覆盖全部列（缺省参数=0），会把 execute_text_chat 实测并 INSERT 的
       input_tokens/output_tokens/latency_ms 覆盖成 0（历史日志 token 全 0 的根因）。

    Returns:
        True 表示更新成功，False 表示失败（log_id 不存在或写入异常）。
    """
    if not log_id or log_id <= 0:
        return False

    _ALLOWED_COLS = (
        "raw_output", "parsed_output", "parse_success", "success_strategy",
        "strategies_tried", "error_message", "input_tokens", "output_tokens", "latency_ms",
    )
    set_parts = []
    values = []
    for key in _ALLOWED_COLS:
        if key not in fields:
            continue
        val = fields[key]
        if key == "raw_output":
            val = _truncate_text(val, 131072)
        elif key == "parsed_output":
            val = _truncate_text(val, 131072)
        elif key == "parse_success":
            val = 1 if val else 0
        elif key == "success_strategy":
            val = _truncate_text(val, 64)
        elif key == "strategies_tried":
            val = int(val or 0)
        elif key == "error_message":
            val = _truncate_text(val, 1024)
        elif key in ("input_tokens", "output_tokens", "latency_ms"):
            val = int(val or 0)
        set_parts.append(f"{key} = ?")
        values.append(val)
    if not set_parts:
        return False
    values.append(int(log_id))

    with _log_conn_lock:
        conn = _get_log_conn()
        try:
            conn.execute(
                "UPDATE llm_call_logs SET " + ", ".join(set_parts) + " WHERE id = ?",
                tuple(values),
            )
            conn.commit()
            return True
        except Exception as write_ex:
            try:
                conn.rollback()
            except Exception:
                _reset_log_conn()
            try:
                from utils.logger import log_manager
                log_manager.get_logger("llm_call_log").error(
                    f"[LLM_LOG_UPDATE_FAILED] {type(write_ex).__name__}: {write_ex}"
                )
            except Exception:
                import sys as _sys
                print(f"[LLM_LOG_UPDATE_FAILED] {write_ex}", file=_sys.stderr)
            return False


'''
content = content[:idx] + new_block + content[next_def:]

# 确保 _truncate_text 工具存在（文件中已有 _truncate 局部函数，这里定义模块级）
if "\ndef _truncate_text(" not in content:
    # 在 update_llm_call_log 之前插入模块级工具函数
    helper = '''\ndef _truncate_text(text: Any, limit: int) -> str:
    if text is None:
        return ""
    s = text if isinstance(text, str) else str(text)
    return s if len(s) <= limit else s[:limit]


'''
    anchor = "def update_llm_call_log(log_id: int, **fields) -> bool:"
    aidx = content.find(anchor)
    assert aidx != -1
    content = content[:aidx] + helper + content[aidx:]

with open(p, "w", encoding="utf-8") as f:
    f.write(content)
print("OK")
