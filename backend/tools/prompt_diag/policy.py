# -*- coding: utf-8 -*-
"""调用策略与诊断模型执行器。

核心机制：
- CallPolicy 决定每次 execute_text_chat 的调用方式（真实调用 / 快照回放）。
- DiagnosticModelExecutor 包装 ModelExecutor，在统一 LLM 入口处拦截：
    - context_analyzer（默认保留）与目标节点 → REAL（真实调用）
    - 其余创作节点 → REPLAY（从快照返回上次输出，零 token 成本）
    - execute_text_to_vector 可按 --no-rag 跳过（返回空 embeddings）
- REPLAY 同样写入 llm_call_logs（success_strategy=diag_replay），并通过
  log bridge 让后续 parse_llm_json 回写同一条记录，保证日志可追溯。
"""

import time
from typing import Dict, Any, List, Optional, Set, Tuple

from core.model_executor import ModelExecutor

# 决策类型
REAL = "real"
REPLAY = "replay"
SKIP = "skip"


class DiagSnapshotError(Exception):
    """快照缺失 / 快照不匹配错误。"""


class CallPolicy:
    """LLM 调用策略判定器。"""

    def __init__(
        self,
        snapshot=None,
        real_all: bool = False,
        only_context: bool = True,
        targets: Optional[Set[str]] = None,
        no_rag: bool = False,
    ):
        self.snapshot = snapshot
        self.real_all = real_all          # --fresh / --with-create：全部真实调用
        self.only_context = only_context  # 默认：context_analyzer 保留真实调用
        self.targets = targets or set()   # --node 指定的 executor_name 集合
        self.no_rag = no_rag              # --no-rag：跳过向量检索
        self._replay_idx: Dict[Tuple[str, str], int] = {}
        self.stats = {REAL: 0, REPLAY: 0, SKIP: 0}

    def decide(self, executor_name: str) -> str:
        """判定本次调用方式。"""
        if self.real_all:
            return REAL
        if executor_name == "context_analyzer":
            # 默认只保留上下文分析的 LLM 调用
            return REAL
        if executor_name in self.targets:
            return REAL
        return REPLAY

    def replay_content(self, executor_name: str, prompt_name: str) -> Tuple[str, Dict[str, Any]]:
        """按 (executor_name, prompt_name) 顺序回放快照中的调用输出。"""
        if self.snapshot is None:
            raise DiagSnapshotError("未加载快照，无法回放调用")
        key = (executor_name, prompt_name)
        idx = self._replay_idx.get(key, 0)
        self._replay_idx[key] = idx + 1
        calls = self.snapshot.calls_by(executor_name, prompt_name)
        if idx >= len(calls):
            raise DiagSnapshotError(
                f"快照缺少第 {idx + 1} 次调用 {executor_name}/{prompt_name}"
                f"（快照共 {len(calls)} 次），请用 --fresh 重新生成快照"
            )
        snap_call = calls[idx]
        return snap_call.get("raw_output", ""), snap_call


class DiagnosticModelExecutor(ModelExecutor):
    """诊断用模型执行器：按 CallPolicy 分发真实调用与快照回放。"""

    def __init__(self, policy: CallPolicy, recorder=None):
        super().__init__()
        self._policy = policy
        self._recorder = recorder
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _new_request_id(self) -> str:
        return f"diag-{int(time.time() * 1000)}-{self._next_seq()}"

    async def execute_text_chat(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 8000,
        **kwargs,
    ) -> Dict[str, Any]:
        executor_name = kwargs.get("executor_name", "")
        prompt_name = kwargs.get("prompt_name", "")
        request_id = self._new_request_id()
        decision = self._policy.decide(executor_name)
        self._policy.stats[decision] = self._policy.stats.get(decision, 0) + 1

        if decision == REAL:
            t0 = time.time()
            kwargs["request_id"] = request_id
            result = await super().execute_text_chat(
                prompt, system_prompt, max_tokens, **kwargs
            )
            if self._recorder is not None:
                self._recorder.record_call(
                    decision=REAL,
                    ts=time.time(),
                    request_id=request_id,
                    executor_name=executor_name,
                    prompt_name=prompt_name,
                    model_name=result.get("model_name", ""),
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                    raw_output=result.get("content", ""),
                    input_tokens=result.get("input_tokens", 0),
                    output_tokens=result.get("output_tokens", 0),
                    latency_ms=result.get("latency_ms", int((time.time() - t0) * 1000)),
                )
            return result

        if decision == REPLAY:
            content, snap_call = self._policy.replay_content(executor_name, prompt_name)
            result = {
                "content": content,
                "model_name": snap_call.get("model_name", "") or "diag_replay",
                "input_tokens": snap_call.get("input_tokens", 0) or 0,
                "output_tokens": snap_call.get("output_tokens", 0) or 0,
                "latency_ms": snap_call.get("latency_ms", 0) or 0,
                "diag_replayed": True,
            }
            self._write_replay_log(
                request_id, kwargs, executor_name, prompt_name,
                system_prompt, prompt, content,
            )
            if self._recorder is not None:
                self._recorder.record_call(
                    decision=REPLAY,
                    ts=time.time(),
                    request_id=request_id,
                    executor_name=executor_name,
                    prompt_name=prompt_name,
                    model_name=result["model_name"],
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                    raw_output=content,
                    input_tokens=result["input_tokens"],
                    output_tokens=result["output_tokens"],
                    latency_ms=result["latency_ms"],
                )
            return result

        # SKIP：仅作兜底（当前版本不会走到，REPLAY 缺失时直接报错）
        result = {"content": "", "diag_skipped": True}
        if self._recorder is not None:
            self._recorder.record_call(
                decision=SKIP, ts=time.time(), request_id=request_id,
                executor_name=executor_name, prompt_name=prompt_name,
                model_name="", system_prompt=system_prompt, user_prompt=prompt,
                raw_output="", input_tokens=0, output_tokens=0, latency_ms=0,
            )
        return result

    async def execute_text_to_vector(
        self,
        texts: list,
        capability_id: str = None,
        is_query: bool = False,
    ) -> Dict[str, Any]:
        """向量检索调用：--no-rag 时跳过（返回空 embeddings），其余放行。"""
        if self._policy.no_rag:
            return {"type": "vector", "embeddings": [], "dim": 0}
        return await super().execute_text_to_vector(texts, capability_id, is_query)

    def _write_replay_log(
        self,
        request_id: str,
        kwargs: Dict[str, Any],
        executor_name: str,
        prompt_name: str,
        system_prompt: str,
        user_prompt: str,
        content: str,
    ) -> None:
        """回放调用写入 llm_call_logs（success_strategy=diag_replay）。

        同时设置 log bridge，使后续 parse_llm_json 回写同一条记录
        （含 parsed_output / parse_success / success_strategy），避免重复插入。
        """
        try:
            from repositories.llm_call_log_repository import add_llm_call_log
            from core.llm_call_context import set_log_bridge, clear_log_bridge

            log_id = add_llm_call_log(
                request_id=request_id,
                script_id=int(kwargs.get("script_id", 0) or 0),
                project_id=int(kwargs.get("project_id", 0) or 0),
                executor_name=executor_name,
                prompt_name=prompt_name,
                model_name="diag_replay",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                raw_output=content,
                parsed_output=None,
                parse_success=0,
                success_strategy="diag_replay",
                strategies_tried=0,
                error_message="",
                input_tokens=0,
                output_tokens=0,
                latency_ms=0,
            )
            if log_id:
                clear_log_bridge()
                set_log_bridge(log_id)
        except Exception:
            # 诊断日志写入失败不影响主流程
            pass
