"""鲁棒的 JSON 解析工具 —— 从 LLM（特别是 Qwen 小模型）输出中提取结构化数据。

包含多种容错策略：
- Markdown 代码块剥离
- NDJSON（每行一个 JSON 对象）解析
- 字符串内裸换行符转义
- 未转义引号修复
- 多余大括号修复
- 从文本中提取 JSON 片段
"""

import re
import json
from typing import Any, Optional, List, Dict, Tuple


# ==============================================================================
# 基础修复工具
# ==============================================================================

def escape_newlines_in_strings(text: str) -> str:
    """转义 JSON 字符串值内的裸换行符。

    Qwen 0.6B 经常在 JSON 字符串值中输出原始换行符，
    导致 json.loads 失败。此方法用状态机跟踪是否在字符串内，
    将字符串内的 \\n / \\r 转义为 \\\\n / \\\\r。
    """
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


def repair_json_quotes(text: str) -> str:
    """修复 JSON 字符串中未转义的引号（启发式修复）。"""
    result = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if not in_string:
            if ch == '"':
                in_string = True
            result.append(ch)
            i += 1
            continue

        # 在字符串内
        if ch == '\\' and i + 1 < len(text):
            result.append(ch)
            result.append(text[i + 1])
            i += 2
            continue
        if ch == '"':
            # 检查这是否是字符串结束：后面应该是 ,:}] 或空白
            j = i + 1
            while j < len(text) and text[j] in ' \t\n\r':
                j += 1
            if j >= len(text) or text[j] in ',:}]':
                in_string = False
                result.append(ch)
                i += 1
                continue
            # 否则是字符串内部的引号，转义它
            result.append('\\')
            result.append(ch)
            i += 1
            continue
        result.append(ch)
        i += 1
    return ''.join(result)


def _strip_markdown_fences(text: str) -> str:
    """去除 markdown 代码块标记（```json ... ``` 或 ``` ... ```）。"""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


# ==============================================================================
# NDJSON 解析
# ==============================================================================

def try_parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    """尝试将文本解析为单个 JSON 对象，多种修复策略。"""
    if not text:
        return None
    text = text.strip()

    # 去除 markdown 标记
    text = _strip_markdown_fences(text)

    if not text or text in ("[", "]"):
        return None

    # 去除行首行尾逗号（JSON数组格式残留）
    if text.startswith(","):
        text = text[1:].strip()
    if text.endswith(","):
        text = text[:-1].strip()
    if not text:
        return None

    # 直接解析
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            return obj[0]
    except json.JSONDecodeError:
        pass

    # 修复双大括号
    fixed = re.sub(r'\{\s*\{', '{', text)
    if fixed != text:
        try:
            obj = json.loads(fixed)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # 转义字符串内裸换行符
    escaped = escape_newlines_in_strings(text)
    if escaped != text:
        try:
            obj = json.loads(escaped)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # 修复未转义引号
    repaired = repair_json_quotes(text)
    if repaired != text:
        try:
            obj = json.loads(repaired)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # 从文本中提取 {...} 对象
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        group = match.group()
        for candidate in (group,
                          escape_newlines_in_strings(group),
                          repair_json_quotes(group)):
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue

    return None


def try_parse_ndjson(text: str) -> Optional[List[Dict[str, Any]]]:
    """尝试将文本按 NDJSON 格式解析（每行一个 JSON 对象）。

    若至少能解析出 1 个对象且所有非空行都能解析，返回对象列表；
    否则返回 None。
    """
    lines = text.split('\n')
    objects: List[Dict[str, Any]] = []
    non_empty_count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        non_empty_count += 1
        obj = try_parse_json_object(stripped)
        if obj is not None:
            objects.append(obj)
        else:
            return None
    if objects and non_empty_count > 0:
        return objects
    return None


# ==============================================================================
# 完整 JSON 响应解析（入口函数）
# ==============================================================================

def parse_json_response(text: str) -> Any:
    """尝试将 LLM 返回的文本解析为 Python 对象。

    依次尝试：
    1. 直接 JSON 解析（去除 markdown 标记后）
    2. NDJSON 格式解析
    3. 修复多余左大括号
    4. 转义字符串内裸换行符
    5. 从文本中提取 JSON 数组/对象
    """
    if not text:
        return None
    cleaned = _strip_markdown_fences(text)

    # 先尝试原始解析
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 尝试 NDJSON 格式
    ndjson_result = try_parse_ndjson(cleaned)
    if ndjson_result is not None:
        return ndjson_result

    # 修复多余的左大括号
    fixed = re.sub(r'\{\s*\{', '{', cleaned)
    if fixed != cleaned:
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    # 转义字符串内的裸换行符后重试
    escaped = escape_newlines_in_strings(cleaned)
    if escaped != cleaned:
        try:
            return json.loads(escaped)
        except json.JSONDecodeError:
            pass

    # 尝试从文本中提取 JSON 数组/对象
    for candidate in (escaped, cleaned, fixed):
        for pattern in (r"\[[\s\S]*\]", r"\{[\s\S]*\}"):
            match = re.search(pattern, candidate)
            if match:
                group = match.group()
                try:
                    return json.loads(group)
                except json.JSONDecodeError:
                    try:
                        return json.loads(escape_newlines_in_strings(group))
                    except json.JSONDecodeError:
                        try:
                            return json.loads(repair_json_quotes(group))
                        except json.JSONDecodeError:
                            continue
    return None


# ==============================================================================
# 流式 JSON 提取（用于边生成边解析）
# ==============================================================================

def extract_json_lines_stream(buffer: str) -> Tuple[List[Dict[str, Any]], str]:
    """从缓冲区中按行提取完整的 JSON 对象（NDJSON 格式）。

    每行一个 JSON 对象，遇到换行符就尝试解析前一行。
    返回 (已解析对象列表, 剩余不完整行的缓冲区)
    """
    results: List[Dict[str, Any]] = []
    lines = buffer.split('\n')
    # 最后一段可能不完整，保留在 buffer 中
    remaining = lines[-1] if lines else ""

    for line in lines[:-1]:
        obj = try_parse_json_object(line)
        if obj is not None:
            results.append(obj)

    return results, remaining


def extract_json_objects_stream(buffer: str) -> Tuple[List[Dict[str, Any]], str]:
    """从缓冲区中提取完整的 JSON 对象，返回 (已解析对象列表, 剩余缓冲区)。

    处理 JSON 数组格式：[{...}, {...}, ...]
    每次发现一个完整的 {...} 对象就尝试解析。
    """
    results = []
    pos = 0
    n = len(buffer)

    while pos < n:
        while pos < n and buffer[pos] in ' \t\n\r,[':
            pos += 1
        if pos >= n:
            break
        if buffer[pos] != '{':
            pos += 1
            continue

        depth = 0
        in_string = False
        escape = False
        obj_start = pos

        while pos < n:
            ch = buffer[pos]
            if escape:
                escape = False
                pos += 1
                continue
            if ch == '\\':
                escape = True
                pos += 1
                continue
            if ch == '"':
                in_string = not in_string
                pos += 1
                continue
            if in_string:
                pos += 1
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    pos += 1
                    obj_str = buffer[obj_start:pos]
                    try:
                        obj = json.loads(obj_str)
                        if isinstance(obj, dict):
                            results.append(obj)
                    except json.JSONDecodeError:
                        try:
                            escaped = escape_newlines_in_strings(obj_str)
                            obj = json.loads(escaped)
                            if isinstance(obj, dict):
                                results.append(obj)
                        except json.JSONDecodeError:
                            pass
                    break
            pos += 1
        else:
            break

    remaining = buffer[pos:] if pos < n else ""
    return results, remaining
