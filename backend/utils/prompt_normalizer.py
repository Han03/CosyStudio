# -*- coding: utf-8 -*-
"""Prompt 注入内容归一化工具。

动态注入到 prompt 的数据（装配上下文/剧情列表/草稿/RAG结果等）可能携带
多余换行符、大片空格、全角空格、零宽/控制字符，会干扰模型对 prompt 区块
边界的理解并浪费 token。本工具提供统一清洗入口。

模式：
- default：普通文本（列表/说明）——全部规则
- preserve_json：JSON 数据块（剧情列表/审查结果）——只做首尾修剪、行尾空白、
  空行压缩、控制字符删除；保留 JSON 缩进与行内空格（值内可能语义相关）
- preserve_md_list：markdown 列表/缩进结构——除行内空格压缩外全部规则
"""

import re

_ZERO_WIDTH_RE = re.compile(
    "[\u200b\u200c\u200d\ufeff\ufeff\ufeff\u00ad]"
)
_CTRL_RE = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
)
_FULLWIDTH_SPACE_RE = re.compile("\u3000")
_MULTI_BLANK_LINE_RE = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")
_TRAILING_WS_RE = re.compile(r"[ \t]+$", re.MULTILINE)
_MULTI_INLINE_SPACE_RE = re.compile(r"[^\S\n]{2,}")


def _clean_common(text: str) -> str:
    """所有模式共用的基础清洗：控制字符、零宽、全角空格、制表符。"""
    text = _CTRL_RE.sub("", text)
    text = _ZERO_WIDTH_RE.sub("", text)
    text = _FULLWIDTH_SPACE_RE.sub("", text)
    text = text.replace("\t", " ")
    return text


def normalize_text_block(
    text: str,
    *,
    mode: str = "default",
) -> str:
    """归一化注入文本块。

    Args:
        text: 待清洗文本
        mode: default / preserve_json / preserve_md_list
    """
    if not text:
        return text

    text = _clean_common(text)
    text = _TRAILING_WS_RE.sub("", text)
    text = _MULTI_BLANK_LINE_RE.sub("\n\n", text)

    if mode == "preserve_json":
        # JSON：保留缩进与行内空格（字符串值内可能语义相关）
        return text.strip()

    if mode == "preserve_md_list":
        # markdown 列表：保留有序缩进，不压缩行内空格
        return text.strip()

    # default：行内连续空格压缩为单个
    text = _MULTI_INLINE_SPACE_RE.sub(" ", text)
    return text.strip()
