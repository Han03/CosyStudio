# -*- coding: utf-8 -*-
"""三层事件捕获（安装/卸载）：

1. LLM 调用 —— 包装 core.model_executor.ModelExecutor.execute_text_chat
   （系统所有 executor 与 service 的 LLM 调用统一出口）。
2. 执行器步骤 —— 包装 webnovel.pipeline.executors 中每个继承 BaseExecutor
   的类的 execute（每个节点一步）。
3. DB 写 —— 将 repositories.base_repository._conn 与
   services.vector_store.sqlite_store._conn 替换为记录型代理：
   捕获 INSERT/UPDATE/DELETE/REPLACE（含参数），并关联当前步骤/LLM 调用。
   说明：conda 的 sqlite3 为 SQLITE_OMIT_TRACE 编译（set_trace_callback 静默无效）
   且 Connection 类不可变（无法 patch 类方法），故采用实例代理方案；
   llm 日志库（app_llm_logs.db）使用独立连接，不受代理影响，天然无噪音。

全部为运行时 monkey-patch，不修改业务代码；uninstall() 恢复原样。
"""

import time

_RESTORE: list = []


def _is_write_sql(sql: str) -> bool:
    s = (sql or "").lstrip().upper()
    return s.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))


def _patch_execute_text_chat(recorder):
    """包装统一 LLM 入口。"""
    import core.model_executor as me

    orig = me.ModelExecutor.execute_text_chat

    async def wrapped(self, prompt: str, system_prompt: str = "", max_tokens: int = 8000, **kwargs):
        from core.llm_call_context import get_current_llm_context
        ctx = get_current_llm_context()
        executor_name = (ctx.executor_name if ctx else "") or kwargs.get("executor_name", "") or ""
        prompt_name = (ctx.prompt_name if ctx else "") or kwargs.get("prompt_name", "") or ""
        started = time.time()
        try:
            result = await orig(self, prompt, system_prompt=system_prompt, max_tokens=max_tokens, **kwargs)
            content = ""
            if isinstance(result, dict):
                content = result.get("content", "")
            recorder.record_llm_call({
                "executor_name": executor_name,
                "prompt_name": prompt_name,
                "system_prompt": system_prompt or "",
                "user_prompt": prompt or "",
                "raw_output": content or "",
                "model_name": (result.get("model_name", "") if isinstance(result, dict) else "") or "",
                "input_tokens": int((result.get("input_tokens") or 0) if isinstance(result, dict) else 0),
                "output_tokens": int((result.get("output_tokens") or 0) if isinstance(result, dict) else 0),
                "latency_ms": int((result.get("latency_ms") or 0) if isinstance(result, dict) else 0),
            })
            return result
        except Exception as exc:
            recorder.record_llm_call({
                "executor_name": executor_name,
                "prompt_name": prompt_name,
                "system_prompt": system_prompt or "",
                "user_prompt": prompt or "",
                "error": f"{type(exc).__name__}: {exc}",
                "latency_ms": int((time.time() - started) * 1000),
            })
            raise

    me.ModelExecutor.execute_text_chat = wrapped
    _RESTORE.append(("model_executor.execute_text_chat", lambda: setattr(
        me.ModelExecutor, "execute_text_chat", orig)))


def _patch_executor_executes(recorder):
    """包装每个 executor 类的 execute（基类方法被子类覆盖，须逐个 patch）。"""
    from webnovel.pipeline.base_executor import BaseExecutor
    import webnovel.pipeline.executors as _ex_mod  # 触发全部 executor 模块加载

    patched: set = set()
    for name in dir(_ex_mod):
        obj = getattr(_ex_mod, name)
        if not isinstance(obj, type) or not issubclass(obj, BaseExecutor) or obj is BaseExecutor:
            continue
        if obj in patched:
            continue
        if not hasattr(obj, "execute"):
            continue
        patched.add(obj)
        orig_execute = obj.execute

        async def wrapped_execute(self, context, _orig=orig_execute, _cls=obj):
            step_name = getattr(self, "step_name", "") or _cls.__name__
            recorder.set_step(step_name)
            started = time.time()
            try:
                result = await _orig(self, context)
                summary = getattr(result, "step_summary", "") or ""
                error = getattr(result, "error_message", "") or ""
                success = bool(getattr(result, "success", True))
                recorder.record_step(
                    step_name, started, time.time(), success,
                    error=error, summary=summary,
                    llm_seqs=list(recorder.llm_seqs),
                    db_seqs=list(recorder.db_seqs),
                )
                return result
            except Exception as exc:
                recorder.record_step(
                    step_name, started, time.time(), False,
                    error=f"{type(exc).__name__}: {exc}",
                    llm_seqs=list(recorder.llm_seqs),
                    db_seqs=list(recorder.db_seqs),
                )
                recorder.record_error(f"executor:{step_name}", exc)
                raise
            finally:
                recorder.clear_step()

        setattr(obj, "execute", wrapped_execute)
        _RESTORE.append((f"executor.{obj.__name__}.execute",
                         lambda _o=obj, _e=orig_execute: setattr(_o, "execute", _e)))


def _record_write(rec, sql, params):
    if isinstance(sql, str) and _is_write_sql(sql):
        try:
            rec.record_db_write(sql, params)
        except Exception:
            pass


class _DiagCursorProxy:
    """游标代理：execute/executemany 记录写语句，其余转发。"""

    def __init__(self, real, rec):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_rec", rec)

    def __getattr__(self, name):
        return getattr(self._real, name)

    def execute(self, sql, parameters=None):
        _record_write(self._rec, sql, parameters)
        if parameters is None:
            return self._real.execute(sql)
        return self._real.execute(sql, parameters)

    def executemany(self, sql, seq_of_parameters):
        _record_write(self._rec, sql, seq_of_parameters)
        return self._real.executemany(sql, seq_of_parameters)

    @property
    def connection(self):
        return self._real.connection


class _DiagConnectionProxy:
    """连接代理：execute/executemany/cursor 记录写语句，其余属性与方法转发到真实连接。

    用于替换 repositories.base_repository._conn 与
    services.vector_store.sqlite_store._conn（不可变 sqlite3.Connection 无法
    patch 类方法，故用实例代理）。
    """

    def __init__(self, real, rec):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_rec", rec)

    def __getattr__(self, name):
        return getattr(self._real, name)

    def __setattr__(self, name, value):
        if name in ("_real", "_rec"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._real, name, value)

    # ---- 记录点 ----
    def execute(self, sql, parameters=None):
        _record_write(self._rec, sql, parameters)
        if parameters is None:
            return self._real.execute(sql)
        return self._real.execute(sql, parameters)

    def executemany(self, sql, seq_of_parameters):
        _record_write(self._rec, sql, seq_of_parameters)
        return self._real.executemany(sql, seq_of_parameters)

    def executescript(self, script):
        _record_write(self._rec, script, None)
        return self._real.executescript(script)

    def cursor(self):
        return _DiagCursorProxy(self._real.cursor(), self._rec)

    # ---- 事务上下文（with conn:）----
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self._real.__exit__(*exc)


_PROXY_REALS: dict = {}


def _patch_db_proxy(recorder):
    """替换 app.db 主连接 与 RAG 向量库连接的全局 _conn 为代理。"""
    from repositories import base_repository as br
    from services.vector_store import sqlite_store as vs

    real_br = br._get_conn()
    real_vs = vs._get_conn()
    _PROXY_REALS["br"] = real_br
    _PROXY_REALS["vs"] = real_vs
    br._conn = _DiagConnectionProxy(real_br, recorder)
    vs._conn = _DiagConnectionProxy(real_vs, recorder)

    def _restore_br():
        setattr(br, "_conn", _PROXY_REALS.get("br", real_br))

    def _restore_vs():
        setattr(vs, "_conn", _PROXY_REALS.get("vs", real_vs))

    _RESTORE.append(("base_repository._conn", _restore_br))
    _RESTORE.append(("sqlite_store._conn", _restore_vs))


def install(recorder):
    """安装三层捕获（幂等：重复调用先卸载）。"""
    uninstall()
    _patch_execute_text_chat(recorder)
    _patch_executor_executes(recorder)
    _patch_db_proxy(recorder)
    return recorder


def uninstall():
    """恢复所有被 patch 的原函数。"""
    while _RESTORE:
        _, restore = _RESTORE.pop()
        try:
            restore()
        except Exception:
            pass
