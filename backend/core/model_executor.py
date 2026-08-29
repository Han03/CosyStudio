import asyncio
import json
import time
import numpy as np
import io
from typing import Dict, Any, Optional, AsyncGenerator

from models.model_capability_manager import capability_manager
from core.global_manager import global_manager
from core.config_manager import get_config, get_model_capabilities
from core.llm_call_context import (
    get_current_llm_context,
    update_current_llm_context,
    _gen_request_id,
    clear_log_bridge,
    set_log_bridge,
)
from utils.logger import log_manager

_logger = log_manager.get_logger("model_executor")

# 🔴 本地模型推理全局串行锁（模块级，跨 ModelExecutor 实例共享）。
# 本地 Qwen/Embedding/Reranker/CosyVoice/DreamLite 均为单实例模型，不支持多线程并发推理：
# 多个创作任务（如同时打开两个剧本编辑器做智能创作）若并发调用会导致
# CUDA 状态竞争、显存 OOM 或输出串流。此锁确保本地推理严格串行；
# 云端能力（httpx 请求）不受此锁限制，仍可并行。
_LOCAL_INFERENCE_LOCK = asyncio.Lock()


class ModelExecutor:
    def __init__(self):
        self._active_capabilities = {}

    async def execute_text_chat(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 8000,
        **kwargs,
    ) -> Dict[str, Any]:
        """执行文本聊天，返回完整结果。

        🔴【统一 LLM 日志入口 —— 必须记录】
          无论调用方后续是否走 parse_llm_json，这里作为所有 execute_text_chat 调用的
          统一出口都会先落一条"调用维度"的日志（含 prompt/model/tokens/latency/报错 等），
          保证"出错后也能通过 llm_call_logs 分析原因"的硬约束不被破坏。

          写入使用 llm_call_log 模块的独立 sqlite3 连接（FOREIGN_KEYS=OFF + synchronous=FULL），
          不受主事务/项目级联删除/脚本删除影响，永久保留。
        """
        import time as _time

        # 🔴 清除上次调用可能残留的桥接 log_id，防止跨调用污染
        clear_log_bridge()

        ctx = get_current_llm_context()
        created_ctx = False
        if ctx is None:
            from core.llm_call_context import LLMCallContext
            ctx = LLMCallContext()
            ctx.request_id = kwargs.get("request_id", "") or _gen_request_id()
            ctx.script_id = int(kwargs.get("script_id", 0) or 0)
            ctx.project_id = int(kwargs.get("project_id", 0) or 0)
            ctx.executor_name = kwargs.get("executor_name", "")
            ctx.prompt_name = kwargs.get("prompt_name", "")
            from core.llm_call_context import set_current_llm_context
            set_current_llm_context(ctx)
            created_ctx = True

        # 统一入口落日志兜底：无论下面模型调用成功/失败/抛异常，finally 都会记
        log_raw_output = ""
        log_error_msg = ""
        log_parse_success = False
        log_model_name = ""
        log_input_tok = 0
        log_output_tok = 0
        log_latency_ms = 0

        try:
            ctx.system_prompt = ctx.system_prompt or system_prompt
            ctx.user_prompt = ctx.user_prompt or prompt
            ctx.start_time = ctx.start_time or _time.time()

            content = ""
            input_tok = 0
            output_tok = 0
            model_name = ""
            error_msg = ""

            # 检查调用点模型覆盖配置
            call_point_override = None
            executor_name = kwargs.get("executor_name", "")
            if executor_name:
                from core.config_manager import get_call_point_model
                call_point_override = get_call_point_model(executor_name)
                if call_point_override:
                    _logger.info(
                        f"调用点覆盖生效: {executor_name} -> "
                        f"{call_point_override['platform_code']}/{call_point_override['model_code']}"
                    )

            async for chunk in self.execute_text_predict(
                prompt=prompt,
                system_prompt=system_prompt,
                stream=True,
                capability_id=kwargs.get("capability_id"),
                generate_params=kwargs.get("generate_params"),
                max_tokens=max_tokens,
                call_point_override=call_point_override,
            ):
                if chunk.get("type") == "text":
                    content += chunk.get("content", "")
                elif chunk.get("type") == "error":
                    error_msg = chunk.get("message", "未知错误")
                    log_error_msg = error_msg
                    return {"error": error_msg}
                elif chunk.get("type") == "finish":
                    input_tok = int(chunk.get("input_tokens", 0) or 0)
                    output_tok = int(chunk.get("output_tokens", 0) or 0)
                    model_name = chunk.get("model_name", "") or chunk.get("model", "") or model_name
                    break

            latency_ms = int((_time.time() - ctx.start_time) * 1000) if ctx.start_time else 0

            update_current_llm_context(
                model_name=model_name,
                input_tokens=input_tok,
                output_tokens=output_tok,
                latency_ms=latency_ms,
            )

            log_raw_output = content
            log_model_name = model_name
            log_input_tok = input_tok
            log_output_tok = output_tok
            log_latency_ms = latency_ms
            log_parse_success = False

            result: Dict[str, Any] = {"content": content}
            if model_name:
                result["model_name"] = model_name
            if input_tok or output_tok:
                result["input_tokens"] = input_tok
                result["output_tokens"] = output_tok
            if latency_ms:
                result["latency_ms"] = latency_ms
            return result
        except Exception as ex:
            log_error_msg = f"execute_text_chat 异常: {ex}"
            raise
        finally:
            # =======================================
            #  🔴 统一入口：LLM 调用结束必写日志（兜底）
            # =======================================
            try:
                ctx.finish_latency()
                # 上下文里如果有更完整的值，优先用上下文
                final_script_id = int(ctx.script_id or 0)
                final_project_id = int(ctx.project_id or 0)
                final_request_id = ctx.request_id or ""
                final_executor = ctx.executor_name or ""
                final_prompt_name = ctx.prompt_name or ""
                final_system_prompt = ctx.system_prompt or system_prompt
                final_user_prompt = ctx.user_prompt or prompt
                final_model = log_model_name or ctx.model_name or ""
                final_in_tok = log_input_tok or ctx.input_tokens or 0
                final_out_tok = log_output_tok or ctx.output_tokens or 0
                final_latency = log_latency_ms or ctx.latency_ms or 0
                final_err = log_error_msg

                from repositories.llm_call_log_repository import add_llm_call_log
                log_id = add_llm_call_log(
                    request_id=final_request_id,
                    script_id=final_script_id,
                    project_id=final_project_id,
                    executor_name=final_executor,
                    prompt_name=final_prompt_name,
                    model_name=final_model,
                    system_prompt=final_system_prompt,
                    user_prompt=final_user_prompt,
                    raw_output=log_raw_output,
                    parsed_output=None,
                    parse_success=bool(log_parse_success),
                    success_strategy="model_executor_unified_entry",
                    strategies_tried=0,
                    error_message=final_err,
                    input_tokens=int(final_in_tok or 0),
                    output_tokens=int(final_out_tok or 0),
                    latency_ms=int(final_latency or 0),
                )
                # 🔴 将 log_id 通过桥接 ContextVar 传递绐后续 parse_llm_json，
                #    使其 UPDATE 同一条记录而非重复 INSERT。
                if log_id and log_id > 0:
                    ctx.log_id = log_id
                    set_log_bridge(log_id)
            except Exception as _log_ex:
                # 日志写入绝对不能影响主流程，异常只记录后吞掉
                try:
                    _logger.error(f"[MODEL_EXECUTOR_LOG_WRITE_FAILED] {type(_log_ex).__name__}: {_log_ex}")
                except Exception:
                    import sys as _sys
                    print(f"[MODEL_EXECUTOR_LOG_WRITE_FAILED] {_log_ex}", file=_sys.stderr)

            if created_ctx:
                try:
                    from core.llm_call_context import set_current_llm_context
                    set_current_llm_context(None)
                except Exception:
                    pass

    async def execute_text_predict(
        self,
        prompt: str,
        system_prompt: str = "",
        stream: bool = True,
        capability_id: str = None,
        generate_params: dict = None,
        max_tokens: int = None,
        call_point_override: dict = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行文本预测能力。

        Args:
            call_point_override: 调用点模型覆盖配置 {platform_code, model_code}，
                若提供则优先使用，失败后回退到默认能力优先级。
        """
        capabilities = capability_manager.get_capabilities_by_type("text_predict")
        
        if capability_id:
            all_capabilities = get_model_capabilities().get("text_predict", [])
            capability = next((c for c in all_capabilities if c.get("id") == capability_id), None)
            if capability:
                capabilities = [capability]

        # 调用点覆盖：构造临时 capability 插入到列表最前面
        if call_point_override:
            override_cap = {
                "id": f"call_point_override_{call_point_override['platform_code']}_{call_point_override['model_code']}",
                "platform_code": call_point_override["platform_code"],
                "model_code": call_point_override["model_code"],
                "priority": 999,
                "enabled": True,
                "description": f"调用点覆盖: {call_point_override['platform_code']}/{call_point_override['model_code']}",
            }
            capabilities = [override_cap] + capabilities
        
        for capability in capabilities:
            try:
                _logger.info(f"尝试使用文本预测能力: {capability.get('id')}")
                async for chunk in self._execute_text_predict_capability(
                    capability, prompt, system_prompt, stream, capability_id is not None or call_point_override is not None, generate_params, max_tokens
                ):
                    yield chunk
                return
            except Exception as e:
                _logger.error(f"文本预测能力 {capability.get('id')} 执行失败: {e}")
                continue
        
        yield {"type": "error", "message": "没有可用的文本预测能力"}

    def is_cloud_capability(self, capability_id: str) -> bool:
        """判断指定能力是否为云端能力"""
        if not capability_id:
            return False
        all_capabilities = get_model_capabilities().get("text_to_speech", [])
        capability = next((c for c in all_capabilities if c.get("id") == capability_id), None)
        if not capability:
            return False
        return capability.get("platform_code", "local") != "local"

    async def execute_text_to_speech(
        self,
        text: str,
        stream: bool = True,
        capability_id: str = None,
        agent_id: str = None,
        tone: str = "",
        instruction: str = "",
        seed: int = 0,
        extra_params: dict = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行语音合成能力"""
        capabilities = capability_manager.get_capabilities_by_type("text_to_speech")
        
        if capability_id:
            all_capabilities = get_model_capabilities().get("text_to_speech", [])
            capability = next((c for c in all_capabilities if c.get("id") == capability_id), None)
            if capability:
                capabilities = [capability]
        elif agent_id:
            # 本地模式（指定 agent_id 但无 capability_id）：只尝试本地 TTS 能力，避免误调用云端
            capabilities = [c for c in capabilities if c.get("platform_code") == "local"]
        
        last_error = None
        for capability in capabilities:
            try:
                _logger.info(f"尝试使用语音合成能力: {capability.get('id')}")
                async for chunk in self._execute_tts_capability(capability, text, stream, capability_id is not None, agent_id, tone, instruction, seed, extra_params):
                    yield chunk
                return
            except Exception as e:
                last_error = str(e)
                _logger.error(f"语音合成能力 {capability.get('id')} 执行失败: {e}")
                continue
        
        error_msg = f"没有可用的语音合成能力"
        if last_error:
            error_msg += f": {last_error}"
        yield {"type": "error", "message": error_msg}

    async def execute_text_to_speech_wav(
        self,
        text: str,
        capability_id: str = None,
        agent_id: str = None,
        tone: str = "",
        instruction: str = "",
        seed: int = 0,
        extra_params: dict = None
    ) -> tuple:
        """执行语音合成能力并返回完整WAV音频数据"""
        import base64
        import wave
        from io import BytesIO
        
        pcm_bytes_list = []
        sample_rate = None
        
        async for chunk in self.execute_text_to_speech(
            text, stream=True, capability_id=capability_id,
            agent_id=agent_id, tone=tone, instruction=instruction, seed=seed,
            extra_params=extra_params
        ):
            if chunk.get("type") == "pcm_chunk":
                pcm_data = base64.b64decode(chunk.get("data", ""))
                pcm_bytes_list.append(pcm_data)
                sample_rate = chunk.get("sample_rate")
            elif chunk.get("type") == "error":
                raise ValueError(chunk.get("message", "合成失败"))
        
        if not pcm_bytes_list or sample_rate is None:
            raise ValueError("合成结果为空")
        
        all_pcm = b"".join(pcm_bytes_list)
        
        buf = BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(all_pcm)
        buf.seek(0)
        
        return buf.read(), sample_rate

    async def execute_text_to_image(
        self,
        prompt: str,
        capability_id: str = None
    ) -> Dict[str, Any]:
        """执行文生图能力（同步）"""
        capabilities = capability_manager.get_capabilities_by_type("text_to_image")
        
        if capability_id:
            all_capabilities = get_model_capabilities().get("text_to_image", [])
            capability = next((c for c in all_capabilities if c.get("id") == capability_id), None)
            if capability:
                capabilities = [capability]
        
        for capability in capabilities:
            try:
                _logger.info(f"尝试使用文生图能力: {capability.get('id')}")
                return await self._execute_t2i_capability(capability, prompt, capability_id is not None)
            except Exception as e:
                _logger.error(f"文生图能力 {capability.get('id')} 执行失败: {e}")
                continue
        
        return {"error": "没有可用的文生图能力"}

    async def execute_text_to_vector(
        self,
        texts: list,
        capability_id: str = None,
        is_query: bool = False
    ) -> Dict[str, Any]:
        """执行文本转向量能力（同步）
        
        Args:
            texts: 文本列表
            capability_id: 可选的能力 ID
            is_query: 是否为查询文本（True 时添加 instruction prefix 以提升检索效果）
        """
        capabilities = capability_manager.get_capabilities_by_type("text_to_vector")
        
        if capability_id:
            all_capabilities = get_model_capabilities().get("text_to_vector", [])
            capability = next((c for c in all_capabilities if c.get("id") == capability_id), None)
            if capability:
                capabilities = [capability]
        
        for capability in capabilities:
            try:
                _logger.info(f"尝试使用文本转向量能力: {capability.get('id')}")
                return await self._execute_t2v_capability(capability, texts, capability_id is not None, is_query=is_query)
            except Exception as e:
                _logger.error(f"文本转向量能力 {capability.get('id')} 执行失败: {e}")
                continue
        
        return {"error": "没有可用的文本转向量能力"}

    async def execute_rerank(
        self,
        query: str,
        documents: list,
        top_k: int = 5,
        capability_id: str = None
    ) -> Dict[str, Any]:
        """执行片段重排序能力（同步）
        
        Args:
            query: 查询文本
            documents: 候选片段列表
            top_k: 返回前k个结果
            capability_id: 可选的能力 ID
        """
        capabilities = capability_manager.get_capabilities_by_type("text_rerank")
        
        if capability_id:
            all_capabilities = get_model_capabilities().get("text_rerank", [])
            capability = next((c for c in all_capabilities if c.get("id") == capability_id), None)
            if capability:
                capabilities = [capability]
        
        for capability in capabilities:
            try:
                _logger.info(f"尝试使用片段重排序能力: {capability.get('id')}")
                return await self._execute_rerank_capability(capability, query, documents, top_k, capability_id is not None)
            except Exception as e:
                _logger.error(f"片段重排序能力 {capability.get('id')} 执行失败: {e}")
                continue
        
        return {"error": "没有可用的片段重排序能力"}

    async def _execute_text_predict_capability(
        self,
        capability: Dict[str, Any],
        prompt: str,
        system_prompt: str,
        stream: bool,
        skip_enabled_check: bool = False,
        generate_params: dict = None,
        max_tokens: int = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行具体的文本预测能力"""
        platform_code = capability.get("platform_code")
        model_code = capability.get("model_code")
        
        if platform_code == "local":
            async for chunk in self._call_local_text_predict(model_code, prompt, system_prompt, stream, generate_params, max_tokens):
                yield chunk
        else:
            async for chunk in self._call_cloud_text_predict(platform_code, model_code, prompt, system_prompt, stream, skip_enabled_check, max_tokens):
                yield chunk

    async def _execute_tts_capability(
        self,
        capability: Dict[str, Any],
        text: str,
        stream: bool,
        skip_enabled_check: bool = False,
        agent_id: str = None,
        tone: str = "",
        instruction: str = "",
        seed: int = 0,
        extra_params: dict = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行具体的语音合成能力"""
        platform_code = capability.get("platform_code")
        model_code = capability.get("model_code")
        
        if platform_code == "local":
            async for chunk in self._call_local_tts(model_code, text, stream, agent_id, tone, instruction, seed):
                yield chunk
        else:
            async for chunk in self._call_cloud_tts(platform_code, model_code, text, stream, skip_enabled_check, extra_params):
                yield chunk

    async def _execute_t2i_capability(
        self,
        capability: Dict[str, Any],
        prompt: str,
        skip_enabled_check: bool = False
    ) -> Dict[str, Any]:
        """执行具体的文生图能力"""
        platform_code = capability.get("platform_code")
        model_code = capability.get("model_code")
        
        if platform_code == "local":
            return await self._call_local_t2i(model_code, prompt)
        else:
            return await self._call_cloud_t2i(platform_code, model_code, prompt, skip_enabled_check)

    async def _execute_t2v_capability(
        self,
        capability: Dict[str, Any],
        texts: list,
        skip_enabled_check: bool = False,
        is_query: bool = False
    ) -> Dict[str, Any]:
        """执行具体的文本转向量能力"""
        platform_code = capability.get("platform_code")
        model_code = capability.get("model_code")
        
        if platform_code == "local":
            return await self._call_local_t2v(model_code, texts, is_query=is_query)
        else:
            return await self._call_cloud_t2v(platform_code, model_code, texts, skip_enabled_check)

    async def _execute_rerank_capability(
        self,
        capability: Dict[str, Any],
        query: str,
        documents: list,
        top_k: int,
        skip_enabled_check: bool = False
    ) -> Dict[str, Any]:
        """执行具体的片段重排序能力"""
        platform_code = capability.get("platform_code")
        model_code = capability.get("model_code")
        
        if platform_code == "local":
            return await self._call_local_rerank(model_code, query, documents, top_k)
        else:
            return await self._call_cloud_rerank(platform_code, model_code, query, documents, top_k, skip_enabled_check)

    async def _call_local_text_predict(
        self,
        model_code: str,
        prompt: str,
        system_prompt: str,
        stream: bool,
        generate_params: dict = None,
        max_tokens: int = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """调用本地文本预测模型（参考 /api/text/chat_stream）"""
        from core.model_manager import ensure_qwen_loaded
        from domain.prompts import process_user_message, process_response
        from infrastructure.param_resolver import get_effective_params
        
        if not await asyncio.to_thread(ensure_qwen_loaded):
            raise ValueError("Qwen模型加载失败")
        
        qwen_model = global_manager.qwen_model
        if qwen_model is None:
            raise ValueError("本地Qwen模型不可用")
        
        processed_text = process_user_message(prompt)
        
        if generate_params:
            qwen_params = generate_params
        else:
            qwen_params = get_effective_params({}, "qwen")
        
        # 🔴 调用方指定的 max_tokens 必须覆盖全局默认值，否则输出会被截断
        if max_tokens is not None:
            qwen_params = {**qwen_params, "max_new_tokens": max_tokens}
        
        # 🔴 本地模型不支持并发推理，整个本地调用（含流式消费）必须串行，
        # 否则多个创作任务会同时对同一模型实例 generate/encode 导致崩溃或输出串流。
        async with _LOCAL_INFERENCE_LOCK:
            if stream:
                generator = qwen_model.generate_stream(
                    processed_text,
                    agent_description=system_prompt.strip() if system_prompt else None,
                    generate_params=qwen_params
                )

                # 🔴 同步生成器必须在独立线程中迭代，否则会阻塞 asyncio 事件循环，
                # 导致 WebSocket / API 请求全部卡死。
                # 使用 asyncio.Queue + loop.call_soon_threadsafe 桥接为异步流。
                queue: asyncio.Queue = asyncio.Queue()
                _SENTINEL = object()  # 线程结束标记
                loop = asyncio.get_running_loop()

                def _sync_generator_to_queue(sync_gen):
                    """在独立线程中迭代同步生成器，将 chunk 推入 asyncio.Queue。"""
                    try:
                        for chunk in sync_gen:
                            loop.call_soon_threadsafe(queue.put_nowait, chunk)
                    except Exception as exc:
                        loop.call_soon_threadsafe(queue.put_nowait, {"type": "_error", "content": str(exc)})
                    finally:
                        loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

                async def _read_queue():
                    """从 Queue 异步读取 chunk 并 yield，保持流式传输效果。"""
                    while True:
                        item = await queue.get()
                        if item is _SENTINEL:
                            break
                        if isinstance(item, dict) and item.get("type") == "_error":
                            raise ValueError(item.get("content", "生成错误"))
                        if item.get("type") == "text":
                            yield {"type": "text", "content": item.get("content", ""), "done": False}
                        elif item.get("type") == "correction":
                            yield {"type": "correction", "content": item.get("content", "")}
                        elif item.get("type") == "finish":
                            yield {
                                "type": "finish",
                                "model_name": model_code or "local_qwen",
                                "input_tokens": int(item.get("input_tokens", 0) or 0),
                                "output_tokens": int(item.get("output_tokens", 0) or 0),
                            }
                            break
                        elif item.get("type") == "error":
                            raise ValueError(item.get("content", "生成错误"))

                asyncio.create_task(asyncio.to_thread(_sync_generator_to_queue, generator))
                async for chunk in _read_queue():
                    yield chunk
            else:
                result = await asyncio.to_thread(
                    qwen_model.generate,
                    processed_text,
                    agent_description=system_prompt.strip() if system_prompt else None,
                    generate_params=qwen_params
                )
                yield {"type": "text", "content": result, "done": True}
                yield {
                    "type": "finish",
                    "model_name": model_code or "local_qwen",
                    "input_tokens": 0,
                    "output_tokens": 0,
                }

    async def _request_with_retry(
        self,
        client: 'httpx.AsyncClient',
        method: str,
        url: str,
        max_retries: int = 3,
        **kwargs,
    ) -> 'httpx.Response':
        """带重试的HTTP请求，处理网络错误和服务端瞬时错误（429/5xx）。"""
        import httpx
        import socket
        last_error = None
        for attempt in range(max_retries):
            try:
                response = await client.request(method, url, **kwargs)
                # 对 429(限流) 和 5xx(服务端错误) 进行重试
                if response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                    wait = 2 ** attempt
                    _logger.warning(
                        f"HTTP请求返回{response.status_code}(第{attempt + 1}/{max_retries}次)，{wait}秒后重试: {url}"
                    )
                    await response.aclose()
                    await asyncio.sleep(wait)
                    continue
                return response
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
                    httpx.WriteTimeout, httpx.NetworkError,
                    socket.gaierror, OSError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    _logger.warning(
                        f"HTTP请求网络错误(第{attempt + 1}/{max_retries}次): {type(e).__name__}: {e}，{wait}秒后重试"
                    )
                    await asyncio.sleep(wait)
                else:
                    _logger.error(f"HTTP请求网络错误，已重试{max_retries}次仍失败: {type(e).__name__}: {e}")
        raise last_error

    async def _call_cloud_text_predict(
        self,
        platform_code: str,
        model_code: str,
        prompt: str,
        system_prompt: str,
        stream: bool,
        skip_enabled_check: bool = False,
        max_tokens: int = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """调用云端文本预测API"""
        import httpx
        
        config = get_config()
        platform_keys = config.get("platform_keys", {})
        platform_config = platform_keys.get(platform_code, {})
        
        if not skip_enabled_check and not platform_config.get("enabled", False):
            raise ValueError(f"平台{platform_code}未启用")
        
        api_key = platform_config.get("api_key")
        base_url = platform_config.get("base_url")
        
        if not api_key or not base_url:
            raise ValueError(f"平台{platform_code}配置不完整")
        
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model_code,
            "messages": messages,
            "stream": stream,
        }
        # 🔴 调用方指定的 max_tokens 必须传递给云端 API，否则输出会被模型默认值截断
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        
        # 带重试的HTTP连接（处理 getaddrinfo failed 等瞬时网络错误）
        client = httpx.AsyncClient(timeout=60.0)
        response = None
        try:
            for _attempt in range(3):
                try:
                    if stream:
                        response = await client.send(
                            client.build_request("POST", url, json=payload, headers=headers),
                            stream=True,
                        )
                    else:
                        response = await client.send(
                            client.build_request("POST", url, json=payload, headers=headers),
                        )
                    break
                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
                        httpx.WriteTimeout, httpx.NetworkError) as e:
                    if _attempt < 2:
                        _wait = 2 ** _attempt
                        _logger.warning(
                            f"API请求网络错误(第{_attempt + 1}/3次): {e}，{_wait}秒后重试"
                        )
                        await asyncio.sleep(_wait)
                    else:
                        _logger.error(f"API请求网络错误，已重试3次仍失败: {e}")
                        raise

            if stream:
                if response.status_code != 200:
                    content = await response.aread()
                    try:
                        result = json.loads(content.decode("utf-8"))
                        message = result.get("message", result.get("error", f"API调用失败，状态码: {response.status_code}"))
                    except json.JSONDecodeError:
                        message = f"API调用失败，状态码: {response.status_code}, 响应: {content.decode('utf-8', errors='ignore')[:200]}"
                    raise ValueError(message)

                full_content = ""
                total_prompt_tokens = 0
                total_completion_tokens = 0
                finish_model = model_code
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        json_data = json.loads(data)
                        choices = json_data.get("choices", [])
                        if json_data.get("model"):
                            finish_model = json_data["model"]
                        usage = json_data.get("usage") or {}
                        if usage:
                            total_prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
                            total_completion_tokens = int(usage.get("completion_tokens", 0) or 0)
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content") or ""
                            full_content += content
                            yield {"type": "text", "content": content, "done": False}
                    except json.JSONDecodeError:
                        continue
                yield {
                    "type": "finish",
                    "model_name": finish_model,
                    "input_tokens": total_prompt_tokens,
                    "output_tokens": total_completion_tokens,
                }
            else:
                if response.status_code != 200:
                    try:
                        result = response.json()
                        error_msg = self._extract_api_error(response, result)
                    except Exception:
                        error_msg = response.text[:500] if response.text else f"HTTP {response.status_code}"
                    raise ValueError(f"API调用失败(HTTP {response.status_code}): {error_msg}")

                result = response.json()
                choices = result.get("choices", [])
                content = choices[0].get("message", {}).get("content", "") if choices else ""
                usage = result.get("usage") or {}
                prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
                completion_tokens = int(usage.get("completion_tokens", 0) or 0)
                model_name = result.get("model", model_code)
                yield {"type": "text", "content": content, "done": True}
                yield {
                    "type": "finish",
                    "model_name": model_name,
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                }
        finally:
            if stream and response is not None:
                try:
                    await response.aclose()
                except Exception:
                    pass
            await client.aclose()

    async def _call_local_tts(
        self,
        model_code: str,
        text: str,
        stream: bool,
        agent_id: str = None,
        tone: str = "",
        instruction: str = "",
        seed: int = 0
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """调用本地语音合成模型（参考 /api/audio/synthesize）"""
        import base64
        import os
        
        from core.model_manager import ensure_cosyvoice_loaded
        from infrastructure.param_resolver import get_effective_params
        from core.global_manager import global_manager
        
        if not await asyncio.to_thread(ensure_cosyvoice_loaded):
            raise ValueError("CosyVoice模型加载失败")
        
        cosyvoice_model = global_manager.cosyvoice_model
        if cosyvoice_model is None:
            raise ValueError("本地CosyVoice模型不可用")
        
        speakers = cosyvoice_model.list_speakers()
        
        if not speakers:
            raise ValueError("未找到可用的说话人，请先配置语气音色")
        
        if agent_id:
            from agents.agent_manager import AgentManager
            
            from core.paths import AGENTS_DATA_DIR
            
            if global_manager.agent_manager is None:
                global_manager.agent_manager = AgentManager(AGENTS_DATA_DIR)
            
            agent = global_manager.agent_manager.get_agent(agent_id)
            if agent is None:
                raise ValueError(f"智能体 {agent_id} 不存在")
            
            speed = get_effective_params(agent, "cosyvoice").get("speed", 1.0)
            
            tone_speaker_id = self._resolve_voice_by_tone(agent, tone)
            
            if tone_speaker_id and tone_speaker_id in speakers:
                speaker_id = tone_speaker_id
            elif agent_id in speakers and not tone:
                speaker_id = agent_id
            else:
                raise ValueError("未找到可用的说话人，请先配置语气音色")
        else:
            speed = global_manager.cosyvoice_config.get("speed", 1.0)
            speaker_id = speakers[0]
        
        yield {
            "type": "start",
            "agent_id": agent_id,
            "text": text[:200],
        }
        
        # 🔴 本地 CosyVoice 单实例，合成过程须与其他本地推理串行（见 _LOCAL_INFERENCE_LOCK）
        async with _LOCAL_INFERENCE_LOCK:
            audio_iter = cosyvoice_model.synthesize_pcm(text, speaker_id=speaker_id, speed=speed, instruction=instruction, seed=seed)
        
            sample_rate = None
            chunk_count = 0
            try:
                for audio_chunk in audio_iter:
                    if audio_chunk["type"] == "pcm_chunk":
                        pcm_data = audio_chunk["data"]
                        sample_rate = audio_chunk["sample_rate"]
                        pcm_data = np.clip(pcm_data, -1.0, 1.0)
                        pcm_bytes = (pcm_data * 32767).astype(np.int16).tobytes()
                        pcm_b64 = base64.b64encode(pcm_bytes).decode("ascii")
                        yield {
                            "type": "pcm_chunk",
                            "sample_rate": sample_rate,
                            "chunk_index": chunk_count,
                            "data": pcm_b64,
                        }
                        chunk_count += 1
                    elif audio_chunk["type"] == "pcm_finish":
                        yield {
                            "type": "finish",
                            "sample_rate": sample_rate,
                            "chunk_count": chunk_count,
                        }
                        break
                    elif audio_chunk["type"] == "error":
                        yield {"type": "error", "message": audio_chunk["content"]}
                        break
            except Exception as e:
                _logger.error(f"[ModelExecutor] TTS流式合成异常: {e}")
                import traceback
                _logger.error(traceback.format_exc())
                yield {"type": "error", "message": str(e)}
    
    def _resolve_voice_by_tone(self, agent: dict, tone: str = "") -> str:
        """根据语气选择已注册的 speaker_id。"""
        voice_tones = agent.get("voice_tones", [])
        if not voice_tones:
            return ""
        
        if tone:
            for vt in voice_tones:
                if vt.get("tone") == tone:
                    return vt.get("speaker_id", "")
        
        first_vt = voice_tones[0]
        return first_vt.get("speaker_id", "")

    async def _call_dashscope_tts(
        self,
        api_key: str,
        model_code: str,
        text: str,
        extra_params: dict = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """调用阿里云 DashScope 非实时语音合成 API（支持 cosyvoice-v3.5-flash 等模型）
        
        DashScope 原生 API 格式:
        - endpoint: /api/v1/services/audio/tts/SpeechSynthesizer
        - 请求体: {model, input: {text, voice, format, sample_rate, ...}}
        - 响应: JSON {output: {audio: {url, data}}}
        """
        import httpx
        import base64

        url = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        extra = extra_params or {}
        # 所有参数都在 input 对象内
        input_obj = {
            "text": text,
            "voice": extra.get("voice", "longxiaochun"),
            "format": extra.get("format", "wav"),
            "sample_rate": extra.get("sample_rate", 22050),
        }
        # 合并用户自定义的其他参数（排除已设置的）
        _reserved = {"voice", "format", "sample_rate", "text"}
        for k, v in extra.items():
            if k not in _reserved:
                input_obj[k] = v

        payload = {
            "model": model_code,
            "input": input_obj,
        }

        _logger.info(f"[DashScope TTS] model={model_code}, voice={input_obj['voice']}, "
                     f"format={input_obj['format']}, sample_rate={input_obj['sample_rate']}")

        client = httpx.AsyncClient(timeout=120.0)
        try:
            response = await self._request_with_retry(client, "POST", url, json=payload, headers=headers)
            if response.status_code != 200:
                try:
                    result = response.json()
                    error_msg = (result.get("message") or result.get("error", {}).get("message")
                                 or str(result))
                except Exception:
                    error_msg = response.text[:500] if response.text else f"HTTP {response.status_code}"
                _logger.error(f"[DashScope TTS] API调用失败: status={response.status_code}, body={error_msg}")
                raise ValueError(f"DashScope TTS调用失败(HTTP {response.status_code}): {error_msg}")

            # 响应为 JSON: {output: {audio: {url, data}}, usage: {...}}
            result = response.json()
            audio_info = result.get("output", {}).get("audio", {})
            audio_url = audio_info.get("url")
            audio_b64 = audio_info.get("data")
            sample_rate = input_obj.get("sample_rate", 22050)

            if audio_url:
                # 从 URL 下载音频文件（带重试）
                dl_client = httpx.AsyncClient(timeout=60.0)
                try:
                    audio_resp = await self._request_with_retry(dl_client, "GET", audio_url)
                    if audio_resp.status_code == 200:
                        audio_b64 = base64.b64encode(audio_resp.content).decode("ascii")
                    else:
                        raise ValueError(f"下载DashScope音频失败: HTTP {audio_resp.status_code}")
                finally:
                    await dl_client.aclose()
            
            if not audio_b64:
                raise ValueError(f"DashScope TTS返回中未找到音频数据: {str(result)[:300]}")

            _logger.info(f"[DashScope TTS] 合成成功, request_id={result.get('request_id', 'N/A')}")
            yield {
                "type": "pcm_chunk",
                "sample_rate": sample_rate,
                "chunk_index": 0,
                "data": audio_b64,
            }
            yield {
                "type": "finish",
                "sample_rate": sample_rate,
                "chunk_count": 1,
            }
        finally:
            await client.aclose()

    async def _call_cloud_tts(
        self,
        platform_code: str,
        model_code: str,
        text: str,
        stream: bool,
        skip_enabled_check: bool = False,
        extra_params: dict = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """调用云端语音合成API
        
        路由逻辑:
        - aliyun 平台 → DashScope 原生 TTS API（支持 cosyvoice-v3.5-flash 等新模型）
        - 其他平台 → OpenAI 兼容格式 {base_url}/audio/speech
        
        extra_params 中可包含:
        - voice: 云端声音标识
        - 其他平台特定参数会合并到请求 payload 中
        """
        config = get_config()
        platform_keys = config.get("platform_keys", {})
        platform_config = platform_keys.get(platform_code, {})
        
        if not skip_enabled_check and not platform_config.get("enabled", False):
            raise ValueError(f"平台{platform_code}未启用")
        
        api_key = platform_config.get("api_key")
        base_url = platform_config.get("base_url")
        
        if not api_key or not base_url:
            raise ValueError(f"平台{platform_code}配置不完整")
        
        # aliyun 平台使用 DashScope 原生 TTS API
        if platform_code == "aliyun":
            async for chunk in self._call_dashscope_tts(api_key, model_code, text, extra_params):
                yield chunk
            return
        
        # 其他平台使用 OpenAI 兼容格式
        import httpx
        
        url = f"{base_url}/audio/speech"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        extra = extra_params or {}
        payload = {
            "model": model_code,
            "input": text,
            "voice": extra.get("voice", "zh-CN-XiaoxiaoNeural"),
        }
        for k, v in extra.items():
            if k != "voice" and k not in payload:
                payload[k] = v
        
        client = httpx.AsyncClient(timeout=60.0)
        try:
            response = await self._request_with_retry(client, "POST", url, json=payload, headers=headers)
            if response.status_code != 200:
                try:
                    result = response.json()
                    error_msg = result.get("message") or result.get("error") or str(result)
                except Exception:
                    error_msg = response.text[:500] if response.text else f"HTTP {response.status_code}"
                _logger.error(f"[云端TTS] API调用失败: status={response.status_code}, body={error_msg}")
                raise ValueError(f"云端TTS调用失败(HTTP {response.status_code}): {error_msg}")
            
            import base64
            audio_b64 = base64.b64encode(response.content).decode("ascii")
            yield {
                "type": "pcm_chunk",
                "sample_rate": 24000,
                "chunk_index": 0,
                "data": audio_b64,
            }
            yield {
                "type": "finish",
                "sample_rate": 24000,
                "chunk_count": 1,
            }
        finally:
            await client.aclose()

    async def _call_local_t2i(
        self,
        model_code: str,
        prompt: str
    ) -> Dict[str, Any]:
        """调用本地文生图模型（参考 /api/image/generate）"""
        from core.model_manager import ensure_dreamlite_loaded
        
        if not await asyncio.to_thread(ensure_dreamlite_loaded):
            raise ValueError("DreamLite模型未加载")
        
        dreamlite_model = global_manager.dreamlite_model
        if dreamlite_model is None:
            raise ValueError("本地DreamLite模型不可用")
        
        config = global_manager.dreamlite_config
        
        def _generate_sync():
            return dreamlite_model.generate(
                prompt=prompt,
                num_inference_steps=config.get("num_inference_steps", 4),
                width=config.get("width", 1024),
                height=config.get("height", 1024),
                seed=config.get("seed", 42),
            )
        
        # 🔴 本地 DreamLite 单实例，推理须与其他本地推理串行（见 _LOCAL_INFERENCE_LOCK）
        async with _LOCAL_INFERENCE_LOCK:
            result = await asyncio.get_event_loop().run_in_executor(None, _generate_sync)
        
        if result is None:
            raise ValueError("模型生成返回空结果")
        
        image = result.images[0]
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format="PNG")
        img_byte_arr.seek(0)
        
        import base64
        image_b64 = base64.b64encode(img_byte_arr.read()).decode("ascii")
        
        return {
            "type": "image",
            "data": image_b64,
            "width": config.get("width", 1024),
            "height": config.get("height", 1024)
        }

    async def _call_cloud_t2i(
        self,
        platform_code: str,
        model_code: str,
        prompt: str,
        skip_enabled_check: bool = False
    ) -> Dict[str, Any]:
        """调用云端文生图API"""
        import httpx
        
        config = get_config()
        platform_keys = config.get("platform_keys", {})
        platform_config = platform_keys.get(platform_code, {})
        
        if not skip_enabled_check and not platform_config.get("enabled", False):
            raise ValueError(f"平台{platform_code}未启用")
        
        api_key = platform_config.get("api_key")
        base_url = platform_config.get("base_url")
        
        if not api_key or not base_url:
            raise ValueError(f"平台{platform_code}配置不完整")
        
        url = f"{base_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": model_code,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
        }
        
        client = httpx.AsyncClient(timeout=120.0)
        try:
            response = await self._request_with_retry(client, "POST", url, json=payload, headers=headers)
            if response.status_code != 200:
                try:
                    result = response.json()
                    error_msg = self._extract_api_error(response, result)
                except Exception:
                    error_msg = response.text[:500] if response.text else f"HTTP {response.status_code}"
                raise ValueError(f"API调用失败(HTTP {response.status_code}): {error_msg}")
            
            result = response.json()
            images = result.get("data", [])
            if images:
                return {"type": "image", "url": images[0].get("url"), "data": None}
            return {"error": "未生成图片"}
        finally:
            await client.aclose()

    async def _call_local_t2v(
        self,
        model_code: str,
        texts: list,
        is_query: bool = False
    ) -> Dict[str, Any]:
        """调用本地文本转向量模型"""
        from core.model_manager import ensure_qwen_embedding_loaded
        
        if not await asyncio.to_thread(ensure_qwen_embedding_loaded):
            raise ValueError("本地Qwen-Embedding模型未加载")
        
        embedding_model = global_manager.qwen_embedding_model
        if embedding_model is None:
            raise ValueError("本地Qwen-Embedding模型不可用")
        
        config = global_manager.qwen_embedding_config
        
        # 🔴 本地 Embedding 单实例，encode 须与其他本地推理串行（见 _LOCAL_INFERENCE_LOCK）
        async with _LOCAL_INFERENCE_LOCK:
            embeddings = await asyncio.to_thread(
                embedding_model.encode,
                texts,
                batch_size=config.get("batch_size", 32),
                is_query=is_query,
            )
        
        return {"type": "vector", "embeddings": embeddings, "dim": len(embeddings[0]) if embeddings else 0}

    @staticmethod
    def _extract_api_error(response, result) -> str:
        """从 API 错误响应中提取可读错误信息。
        
        兼容两种格式：顶层 message（部分平台）与嵌套 error.message（OpenAI 兼容格式，
        如阿里云百炼返回 {"error": {"message": ..., "code": ...}}）。
        """
        try:
            err = result.get("error")
            if isinstance(err, dict):
                return str(err.get("message") or err) or "API调用失败"
            return result.get("message") or str(result) or "API调用失败"
        except Exception:
            return f"API调用失败，状态码: {response.status_code}"

    async def _call_cloud_t2v(
        self,
        platform_code: str,
        model_code: str,
        texts: list,
        skip_enabled_check: bool = False
    ) -> Dict[str, Any]:
        """调用云端文本转向量API"""
        import httpx
        
        # 云端 embedding 接口单次请求条数上限（阿里云百炼 OpenAI 兼容端点为 20），
        # 超出会返回 400，故此处分批发送；批量索引场景一次可能传入上百条文本。
        CLOUD_T2V_BATCH_SIZE = 20
        
        config = get_config()
        platform_keys = config.get("platform_keys", {})
        platform_config = platform_keys.get(platform_code, {})
        
        if not skip_enabled_check and not platform_config.get("enabled", False):
            raise ValueError(f"平台{platform_code}未启用")
        
        api_key = platform_config.get("api_key")
        base_url = platform_config.get("base_url")
        
        if not api_key or not base_url:
            raise ValueError(f"平台{platform_code}配置不完整")
        
        url = f"{base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        client = httpx.AsyncClient(timeout=60.0)
        try:
            embeddings = []
            for i in range(0, len(texts), CLOUD_T2V_BATCH_SIZE):
                batch = texts[i:i + CLOUD_T2V_BATCH_SIZE]
                payload = {
                    "model": model_code,
                    "input": batch,
                }
                response = await self._request_with_retry(client, "POST", url, json=payload, headers=headers)
                if response.status_code != 200:
                    try:
                        result = response.json()
                        error_msg = self._extract_api_error(response, result)
                    except Exception:
                        error_msg = response.text[:500] if response.text else f"HTTP {response.status_code}"
                    raise ValueError(f"API调用失败(HTTP {response.status_code}): {error_msg}")
                
                result = response.json()
                # 按 index 排序，防止云端返回顺序与输入不一致导致向量错位
                data = sorted(result.get("data", []), key=lambda item: item.get("index", 0))
                embeddings.extend(item.get("embedding") for item in data)
            return {"type": "vector", "embeddings": embeddings, "dim": len(embeddings[0]) if embeddings else 0}
        finally:
            await client.aclose()

    async def _call_local_rerank(
        self,
        model_code: str,
        query: str,
        documents: list,
        top_k: int
    ) -> Dict[str, Any]:
        """调用本地片段重排序模型"""
        from core.model_manager import ensure_qwen_reranker_loaded
        
        if not await asyncio.to_thread(ensure_qwen_reranker_loaded):
            raise ValueError("本地Qwen-Reranker模型未加载")
        
        reranker_model = global_manager.qwen_reranker_model
        if reranker_model is None:
            raise ValueError("本地Qwen-Reranker模型不可用")
        
        config = global_manager.qwen_reranker_config
        
        # 🔴 本地 Reranker 单实例，打分须与其他本地推理串行（见 _LOCAL_INFERENCE_LOCK）
        async with _LOCAL_INFERENCE_LOCK:
            results = await asyncio.to_thread(
                reranker_model.rerank,
                query,
                documents,
                top_k,
                max_length=config.get("max_length", 1024),
            )
        
        return {"type": "rerank", "results": results}

    async def _call_cloud_rerank(
        self,
        platform_code: str,
        model_code: str,
        query: str,
        documents: list,
        top_k: int,
        skip_enabled_check: bool = False
    ) -> Dict[str, Any]:
        """调用云端片段重排序API。
        
        路由逻辑（与云端 TTS 一致）：
        - aliyun 平台 → DashScope 原生 rerank API（OpenAI 兼容模式下不存在 /rerank 端点，会 404）
        - 其他平台 → OpenAI 兼容格式 {base_url}/rerank
        """
        import httpx
        
        config = get_config()
        platform_keys = config.get("platform_keys", {})
        platform_config = platform_keys.get(platform_code, {})
        
        if not skip_enabled_check and not platform_config.get("enabled", False):
            raise ValueError(f"平台{platform_code}未启用")
        
        api_key = platform_config.get("api_key")
        base_url = platform_config.get("base_url")
        
        if not api_key or not base_url:
            raise ValueError(f"平台{platform_code}配置不完整")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        if platform_code == "aliyun":
            # DashScope 原生接口：query/documents 嵌套在 input 中，top_n 在 parameters 中
            url = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
            payload = {
                "model": model_code,
                "input": {"query": query, "documents": documents},
                "parameters": {"top_n": top_k},
            }
        else:
            url = f"{base_url}/rerank"
            payload = {
                "model": model_code,
                "query": query,
                "documents": documents,
                "top_n": top_k,
            }
        
        client = httpx.AsyncClient(timeout=60.0)
        try:
            response = await self._request_with_retry(client, "POST", url, json=payload, headers=headers)
            if response.status_code != 200:
                try:
                    result = response.json()
                    error_msg = self._extract_api_error(response, result)
                except Exception:
                    error_msg = response.text[:500] if response.text else f"HTTP {response.status_code}"
                raise ValueError(f"API调用失败(HTTP {response.status_code}): {error_msg}")
            
            result = response.json()
            # 兼容 OpenAI 风格与 DashScope 风格两种返回结构
            raw_results = result.get("results") or result.get("output", {}).get("results", [])
            results = []
            for item in raw_results:
                idx = item.get("index", 0)
                results.append({
                    "document": item.get("document") or (documents[idx] if 0 <= idx < len(documents) else ""),
                    "score": float(item.get("relevance_score", item.get("score", 0.0))),
                    "index": idx
                })
            return {"type": "rerank", "results": results}
        finally:
            await client.aclose()


model_executor = ModelExecutor()


def get_model_executor() -> ModelExecutor:
    return model_executor
