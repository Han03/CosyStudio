"""LLM调用上下文：通过ContextVar在统一入口记录调用元数据，供解析器/日志系统读取。"""

from __future__ import annotations

import contextvars
import threading
import uuid
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


@dataclass
class LLMCallContext:
    """一次LLM调用的上下文元数据。"""
    request_id: str = ""
    script_id: int = 0
    project_id: int = 0
    executor_name: str = ""
    prompt_name: str = ""
    model_name: str = ""
    system_prompt: str = ""
    user_prompt: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    start_time: float = 0.0
    platform_code: str = ""
    capability_id: str = ""
    log_id: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    def finish_latency(self) -> None:
        if self.start_time and not self.latency_ms:
            self.latency_ms = int((time.time() - self.start_time) * 1000)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_ctx_var: contextvars.ContextVar[Optional[LLMCallContext]] = contextvars.ContextVar(
    "llm_call_context", default=None
)

# 🔴 桥接 ContextVar：将 model_executor INSERT 产生的 log_id 传递给后续 parse_llm_json，
#    使其能 UPDATE 同一条记录而非重复 INSERT。
#    独立于 _ctx_var，不受 set_current_llm_context(None) 清除主上下文的影响。
_log_bridge_var: contextvars.ContextVar[int] = contextvars.ContextVar("_log_bridge_var", default=0)


def set_log_bridge(log_id: int) -> None:
    """将 log_id 写入桥接 ContextVar（由 model_executor INSERT 后调用）。"""
    _log_bridge_var.set(log_id)


def consume_log_bridge() -> int:
    """读取并清除桥接 ContextVar（由 parse_llm_json 调用），返回 log_id（0 表示无）。"""
    log_id = _log_bridge_var.get()
    _log_bridge_var.set(0)
    return log_id


def clear_log_bridge() -> None:
    """清除桥接 ContextVar（由 execute_text_chat 开头调用，防止上次残留的 stale log_id）。"""
    _log_bridge_var.set(0)


_thread_id = 0
_thread_lock = threading.Lock()


def _gen_request_id() -> str:
    global _thread_id
    with _thread_lock:
        _thread_id += 1
        seq = _thread_id
    ts = int(time.time() * 1000)
    short = uuid.uuid4().hex[:6]
    return f"llm-{ts}-{seq}-{short}"


def get_current_llm_context() -> Optional[LLMCallContext]:
    """获取当前协程/线程的LLM调用上下文，无则返回None。"""
    ctx = _ctx_var.get()
    return ctx


def set_current_llm_context(ctx: Optional[LLMCallContext]) -> None:
    _ctx_var.set(ctx)


@contextmanager
def llm_call_context_scope(**kwargs):
    """同步上下文管理器（非async），通常用于子线程。"""
    ctx = LLMCallContext(**kwargs)
    if not ctx.request_id:
        ctx.request_id = _gen_request_id()
    if not ctx.start_time:
        ctx.start_time = time.time()
    token = _ctx_var.set(ctx)
    try:
        yield ctx
    finally:
        try:
            _ctx_var.reset(token)
        except Exception:
            pass


@asynccontextmanager
async def llm_call_async_scope(**kwargs):
    """异步上下文管理器，包裹ModelExecutor一次调用。

    典型用法：
        async with llm_call_async_scope(
            script_id=sid, executor_name="init_executor", prompt_name="init_protagonist"
        ) as ctx:
            result = await executor.execute_text_chat(prompt=..., system_prompt=...)
            ctx.model_name = result.get("model_name", "")
            ctx.finish_latency()
            ... parse_llm_json 会自动读取ctx ...
    """
    ctx = LLMCallContext(**kwargs)
    if not ctx.request_id:
        ctx.request_id = _gen_request_id()
    if not ctx.start_time:
        ctx.start_time = time.time()
    token = _ctx_var.set(ctx)
    try:
        yield ctx
    finally:
        try:
            ctx.finish_latency()
            _ctx_var.reset(token)
        except Exception:
            pass


def merge_llm_context(**kwargs) -> Dict[str, Any]:
    """合并当前上下文和显式参数（显式参数优先级更高），返回最终用于写日志的字段。

    parse_llm_json中可直接调用：把当前ContextVar的值与函数入参合并，非空优先。
    """
    base: Dict[str, Any] = {}
    ctx = _ctx_var.get()
    if ctx:
        base = {
            "request_id": ctx.request_id,
            "script_id": ctx.script_id,
            "project_id": ctx.project_id,
            "executor_name": ctx.executor_name,
            "prompt_name": ctx.prompt_name,
            "model_name": ctx.model_name,
            "system_prompt": ctx.system_prompt,
            "user_prompt": ctx.user_prompt,
            "input_tokens": ctx.input_tokens,
            "output_tokens": ctx.output_tokens,
            "latency_ms": ctx.latency_ms,
            "log_id": ctx.log_id,
        }

    for k, v in kwargs.items():
        if v is None or v == "" or v == 0:
            continue
        if k in ("system_prompt", "user_prompt"):
            base[k] = v
            continue
        base[k] = v

    return base


def update_current_llm_context(**fields):
    """更新当前LLM调用上下文（例如在拿到结果后回填model_name/tokens）。"""
    ctx = _ctx_var.get()
    if ctx is None:
        return
    for k, v in fields.items():
        if hasattr(ctx, k):
            setattr(ctx, k, v)
