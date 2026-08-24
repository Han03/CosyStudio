import os
import json
import asyncio
import numpy as np
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState

from utils.logger import log_manager
from utils.media_processor import (
    process_image,
    process_audio,
    process_document,
    MAX_IMAGE_SIZE,
    MAX_AUDIO_SIZE,
    MAX_DOCUMENT_SIZE,
)
from core.global_manager import global_manager
from services.chat import (
    handle_text_chat_response,
    send_text_chat_welcome,
    handle_read_aloud_response,
)

router = APIRouter()

AUDIO_HEADER_MARK = b"OMNI_AUDIO:"

MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media")


async def _safe_send_json(websocket: WebSocket, data: dict) -> bool:
    """安全发送 JSON 消息，连接断开时不抛出异常。

    Args:
        websocket: WebSocket 连接
        data: 要发送的数据

    Returns:
        是否发送成功
    """
    try:
        if websocket.client_state != WebSocketState.CONNECTED:
            return False
        await websocket.send_json(data)
        return True
    except (WebSocketDisconnect, RuntimeError, Exception):
        return False


def _save_image_to_media(agent_id: str, image_input) -> Optional[str]:
    """保存图像到 media 目录。返回相对路径。"""
    try:
        image_dir = os.path.join(MEDIA_DIR, agent_id, "images")
        os.makedirs(image_dir, exist_ok=True)
        timestamp = int(time.time())
        filename = f"image_{timestamp}.png"
        filepath = os.path.join(image_dir, filename)
        image_input.save(filepath, format="PNG")
        rel_path = f"{agent_id}/images/{filename}"
        add_log(f"[Media] 图像已保存: {filepath}")
        return rel_path
    except Exception as e:
        add_log(f"[Media] 保存图像失败: {e}", "WARNING")
        return None


def _save_audio_to_media(agent_id: str, audio_np: np.ndarray) -> Optional[str]:
    """保存音频到 media 目录。返回相对路径。"""
    try:
        audio_dir = os.path.join(MEDIA_DIR, agent_id, "audio")
        os.makedirs(audio_dir, exist_ok=True)
        timestamp = int(time.time())
        filename = f"audio_{timestamp}.wav"
        filepath = os.path.join(audio_dir, filename)
        import soundfile as sf
        sf.write(filepath, audio_np, 24000)
        rel_path = f"{agent_id}/audio/{filename}"
        add_log(f"[Media] 音频已保存: {filepath}")
        return rel_path
    except Exception as e:
        add_log(f"[Media] 保存音频失败: {e}", "WARNING")
        return None


def add_log(message: str, level: str = "INFO"):
    try:
        ws_log = log_manager.get_logger("websocket")
        if level == "INFO":
            ws_log.info(message)
        elif level == "WARNING":
            ws_log.warning(message)
        elif level == "ERROR":
            ws_log.error(message)
        else:
            ws_log.info(message)
    except:
        pass
    print(f"[LOG][{level}] {message}")


def ensure_agent_manager():
    """确保智能体管理器已加载"""
    if global_manager.agent_manager is None:
        from agents.agent_manager import AgentManager
        from core.paths import AGENTS_DATA_DIR
        global_manager.agent_manager = AgentManager(AGENTS_DATA_DIR)
        add_log("智能体管理器已加载")
    return global_manager.agent_manager


async def ensure_qwen_model_loaded():
    """确保 Qwen 模型已加载（文本沟通）"""
    from core.model_manager import ensure_qwen_loaded
    return await asyncio.to_thread(ensure_qwen_loaded)


async def ensure_cosyvoice_model_loaded():
    """确保 CosyVoice 模型已加载（文本朗读）"""
    from core.model_manager import ensure_cosyvoice_loaded
    return await asyncio.to_thread(ensure_cosyvoice_loaded)


# ============================================================
#文本分析 WebSocket（Qwen 文本流式 + 可选 CosyVoice 朗读）
# ============================================================

@router.websocket("/api/agents/chat")
async def websocket_chat(websocket: WebSocket, agent_id: str):
    """
   文本分析 WebSocket 端点

    前端连接: ws://host/api/agents/{agent_id}/chat
    前端发送: {"type": "message", "text": "..."}
    后端下发: status / stream_start / stream_chunk / stream_finish / correction / response / pcm_chunk(二进制) / error
    """
    await websocket.accept()
    add_log(f"[WebSocket-Chat] 连接已建立，agent_id={agent_id}")

    mgr = ensure_agent_manager()
    agent = mgr.get_agent(agent_id)

    if agent is None:
        add_log(f"[WebSocket-Chat] 智能体 {agent_id} 不存在", "WARNING")
        await websocket.send_json({"type": "error", "message": f"智能体 {agent_id} 不存在"})
        await websocket.close()
        return

    add_log(f"[WebSocket-Chat] 智能体: {agent.get('name')}")

    await websocket.send_json({
        "type": "status",
        "message": "正在加载模型...",
        "ready": False
    })

    try:
        ok = await ensure_qwen_model_loaded()
        if not ok:
            await websocket.send_json({"type": "error", "message": "Qwen 模型加载失败"})
            await websocket.close()
            return

        await websocket.send_json({
            "type": "status",
            "message": "模型已就绪，正在准备对话...",
            "ready": True
        })

        asyncio.create_task(send_text_chat_welcome(websocket, agent))

    except Exception as e:
        add_log(f"[WebSocket-Chat] 模型加载异常: {e}", "ERROR")
        import traceback
        add_log(traceback.format_exc(), "ERROR")
        await websocket.send_json({"type": "error", "message": f"模型加载异常: {str(e)}"})
        await websocket.close()
        return

    # 创建/复用会话（用于历史管理）
    from domain.conversation import get_conversation_manager
    conv_mgr = get_conversation_manager()
    session = conv_mgr.get_or_create_session(agent_id)

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive(), timeout=600.0)
            except asyncio.TimeoutError:
                add_log("[WebSocket-Chat] 连接超时（10分钟无消息）", "WARNING")
                break

            # 收到断开消息，立即退出
            if data.get("type") == "websocket.disconnect":
                add_log("[WebSocket-Chat] 收到断开消息")
                break

            if "text" in data:
                try:
                    message = json.loads(data["text"])
                except json.JSONDecodeError:
                    add_log("[WebSocket-Chat] 收到无效的 JSON 消息", "WARNING")
                    continue

                message_type = message.get("type")

                if message_type == "message":
                    user_message = message.get("text") or message.get("content") or ""
                    if not user_message.strip():
                        continue
                    add_log(f"[WebSocket-Chat] 收到用户消息: '{user_message[:50]}...'")
                    await handle_text_chat_response(websocket, agent, user_message, session=session)

                elif message_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif message_type == "close":
                    add_log("[WebSocket-Chat] 客户端主动关闭连接")
                    break

                else:
                    add_log(f"[WebSocket-Chat] 未知消息类型: {message_type}")

    except WebSocketDisconnect:
        add_log("[WebSocket-Chat] 连接断开")
    except Exception as e:
        add_log(f"[WebSocket-Chat] 异常: {e}", "ERROR")
        import traceback
        add_log(traceback.format_exc(), "ERROR")
    finally:
        add_log("[WebSocket-Chat] 连接关闭")


# ============================================================
# 文本朗读 WebSocket（CosyVoice TTS：文本输入 → PCM 音频流）
# ============================================================

@router.websocket("/api/agents/read")
async def websocket_read(websocket: WebSocket, agent_id: str):
    """
    文本朗读 WebSocket 端点

    前端连接: ws://host/api/agents/{agent_id}/read
    前端发送: {"type": "message", "text": "..."}
    后端下发: status / stream_start / pcm_chunk(二进制) / pcm_finish / stream_finish / finish / error
    """
    await websocket.accept()
    add_log(f"[WebSocket-Read] 连接已建立，agent_id={agent_id}")

    mgr = ensure_agent_manager()
    agent = mgr.get_agent(agent_id)

    if agent is None:
        add_log(f"[WebSocket-Read] 智能体 {agent_id} 不存在", "WARNING")
        await websocket.send_json({"type": "error", "message": f"智能体 {agent_id} 不存在"})
        await websocket.close()
        return

    add_log(f"[WebSocket-Read] 智能体: {agent.get('name')}")

    await websocket.send_json({
        "type": "status",
        "message": "正在加载模型...",
        "ready": False
    })

    try:
        ok = await ensure_cosyvoice_model_loaded()
        if not ok:
            await websocket.send_json({"type": "error", "message": "CosyVoice 模型加载失败"})
            await websocket.close()
            return

        await websocket.send_json({
            "type": "status",
            "message": "模型已就绪，可以开始朗读",
            "ready": True
        })

    except Exception as e:
        add_log(f"[WebSocket-Read] 模型加载异常: {e}", "ERROR")
        import traceback
        add_log(traceback.format_exc(), "ERROR")
        await websocket.send_json({"type": "error", "message": f"模型加载异常: {str(e)}"})
        await websocket.close()
        return

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive(), timeout=600.0)
            except asyncio.TimeoutError:
                add_log("[WebSocket-Read] 连接超时（10分钟无消息）", "WARNING")
                break

            if "text" in data:
                try:
                    message = json.loads(data["text"])
                except json.JSONDecodeError:
                    add_log("[WebSocket-Read] 收到无效的 JSON 消息", "WARNING")
                    continue

                message_type = message.get("type")

                if message_type == "message":
                    text = message.get("text") or message.get("content") or ""
                    if not text.strip():
                        continue
                    add_log(f"[WebSocket-Read] 收到朗读请求: '{text[:50]}...'")
                    await handle_read_aloud_response(websocket, agent, text)

                elif message_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif message_type == "close":
                    add_log("[WebSocket-Read] 客户端主动关闭连接")
                    break

                else:
                    add_log(f"[WebSocket-Read] 未知消息类型: {message_type}")

    except WebSocketDisconnect:
        add_log("[WebSocket-Read] 连接断开")
    except Exception as e:
        add_log(f"[WebSocket-Read] 异常: {e}", "ERROR")
        import traceback
        add_log(traceback.format_exc(), "ERROR")
    finally:
        add_log("[WebSocket-Read] 连接关闭")


# ============================================================
# 日志 WebSocket（实时日志推送）
# ============================================================

@router.websocket("/api/logs/ws")
async def websocket_logs(websocket: WebSocket, category: Optional[str] = Query(None)):
    """
    实时日志 WebSocket 端点

    前端连接: ws://host/api/logs/ws?category=system
    参数:
      - category: 可选，按业务分类过滤日志（如 system, websocket, task, model 等）

    后端下发:
      - {"type": "log", "timestamp": 1234567890, "level": "INFO", "category": "system", "message": "..."}
      - {"type": "history", "logs": [...]}  (连接建立后发送历史日志
    """
    await websocket.accept()

    log_queue = asyncio.Queue()
    ws_loop = asyncio.get_event_loop()

    def log_callback(log_entry):
        if category and log_entry.get("category") != category:
            return
        try:
            ws_loop.call_soon_threadsafe(
                lambda: log_queue.put_nowait(log_entry)
            )
        except Exception:
            pass

    log_manager.add_ws_callback(log_callback)

    try:
        history = log_manager.get_recent_logs(limit=100, category=category)
        await websocket.send_json({
            "type": "history",
            "logs": history
        })

        async def receive_loop():
            while True:
                try:
                    data = await websocket.receive_text()
                    message = json.loads(data)
                    msg_type = message.get("type")
                    if msg_type == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif msg_type == "close":
                        break
                except WebSocketDisconnect:
                    break
                except Exception:
                    break

        async def send_loop():
            while True:
                log_entry = await log_queue.get()
                try:
                    await websocket.send_json({
                        "type": "log",
                        **log_entry
                    })
                except Exception:
                    break

        receive_task = asyncio.create_task(receive_loop())
        send_task = asyncio.create_task(send_loop())

        done, pending = await asyncio.wait(
            [receive_task, send_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        log_manager.remove_ws_callback(log_callback)


# ============================================================
# 剧本生成 WebSocket（实时推送剧本生成进度和台词）
# ============================================================

@router.websocket("/api/books/scripts/ws")
async def websocket_script_generation(websocket: WebSocket, script_id: int):
    """
    剧本生成 WebSocket 端点

    前端连接: ws://host/api/books/scripts/{script_id}/ws

    后端下发:
      - status: {"type": "status", "status": "running/ready/failed", "progress": 0-100, "message": "...", "total_lines": 0}
      - lines_added: {"type": "lines_added", "lines": [...]}
      - finish: {"type": "finish", "total_lines": 0}
      - error: {"type": "error", "message": "..."}
      - audio_generated: {"type": "audio_generated", "line_id": 123, "script_id": 456}
    """
    await websocket.accept()
    add_log(f"[WebSocket-Script] 连接已建立，script_id={script_id}")

    from infrastructure.websocket_broadcast import ws_broadcast_manager
    from services.script_service import get_script_service
    from repositories import get_script_line_count, get_script, get_script_lines
    from domain.agent_tasks import agent_task_manager

    service = get_script_service()
    script = service.get_script(script_id)

    if script is None:
        add_log(f"[WebSocket-Script] 剧本不存在: script_id={script_id}", "WARNING")
        await _safe_send_json(websocket, {"type": "error", "message": "剧本不存在"})
        await websocket.close()
        return

    ws_broadcast_manager.register_connection(script_id, websocket)
    add_log(f"[WebSocket-Script] 剧本: {script.get('name')} (status={script.get('status')})")

    total_lines = get_script_line_count(script_id)
    current_status = script.get("status", "pending")
    task_id = script.get("task_id", "")

    progress = 0
    message = ""
    if task_id:
        task = agent_task_manager.get_task(task_id)
        if task:
            progress = task.get("progress", 0)
            message = task.get("message", "")
    
    if not message and script.get("progress_message"):
        message = script["progress_message"]

    await _safe_send_json(websocket, {
        "type": "status",
        "status": current_status,
        "progress": progress,
        "message": message,
        "total_lines": total_lines,
    })

    if current_status == "ready":
        add_log(f"[WebSocket-Script] 剧本已就绪，保持连接等待操作")
        await _safe_send_json(websocket, {
            "type": "status",
            "status": "ready",
            "progress": 100,
            "message": "剧本已就绪，可选择章节生成台词",
            "total_lines": total_lines,
        })

    if current_status == "failed":
        add_log(f"[WebSocket-Script] 剧本状态为failed，发送错误状态后保持连接（避免重连循环）")
        await _safe_send_json(websocket, {
            "type": "error",
            "message": message or "剧本生成失败",
            "permanent_failure": True,
        })
        # 不再 close 连接，也不 return：进入下方的 receive/send loop 保持连接，
        # 这样用户重试初始化时 broadcast_init_progress 仍能推送到此连接

    import asyncio
    loop = asyncio.get_event_loop()
    line_queue = service.get_generation_queue(script_id)
    status_queue = asyncio.Queue()
    is_running = True
    generate_task = None
    last_line_id = 0
    listener_id = f"ws_{id(websocket)}"

    lines = get_script_lines(script_id)
    if lines:
        last_line_id = max(l["id"] for l in lines)

    def queue_listener(event_type, data):
        if not is_running:
            return
        try:
            if event_type == "lines_added":
                add_log(f"[WebSocket-Script] 收到事件: {event_type}, {len(data['lines'])} 条语句")
                loop.call_soon_threadsafe(
                    lambda: line_queue.put_nowait(data["lines"])
                )
        except Exception as e:
            add_log(f"[WebSocket-Script] 队列监听器异常: {e}", "ERROR")

    service.register_listener(script_id, listener_id, queue_listener)

    async def generate_script_task():
        try:
            book_id = script.get("book_id")
            success = await service.generate_script_stream(
                script_id, book_id,
            )
            if is_running:
                try:
                    loop.call_soon_threadsafe(
                        lambda: status_queue.put_nowait(("finish" if success else "error", "full_script"))
                    )
                except Exception:
                    pass
        except Exception as e:
            add_log(f"[WebSocket-Script] 生成任务异常: {e}", "ERROR")
            import traceback
            add_log(traceback.format_exc(), "ERROR")
            if is_running:
                try:
                    loop.call_soon_threadsafe(
                        lambda: status_queue.put_nowait(("error", str(e)))
                    )
                except Exception:
                    pass

    async def generate_chapter_task(chapter_index: int):
        try:
            if global_manager.is_model_busy():
                if is_running:
                    try:
                        loop.call_soon_threadsafe(
                            lambda: status_queue.put_nowait(("error", "系统繁忙，请稍后再试"))
                        )
                    except Exception:
                        pass
                return

            if not global_manager.try_acquire_model("qwen"):
                if is_running:
                    try:
                        loop.call_soon_threadsafe(
                            lambda: status_queue.put_nowait(("error", "系统繁忙，请稍后再试"))
                        )
                    except Exception:
                        pass
                return

            try:
                success = await service.generate_chapter_script_stream(
                    script_id, chapter_index,
                )
                if is_running:
                    try:
                        loop.call_soon_threadsafe(
                            lambda: status_queue.put_nowait(("finish", "chapter"))
                        )
                    except Exception:
                        pass
            finally:
                global_manager.release_model()
        except Exception as e:
            global_manager.release_model()
            add_log(f"[WebSocket-Script] 章节生成任务异常: {e}", "ERROR")
            import traceback
            add_log(traceback.format_exc(), "ERROR")
            if is_running:
                try:
                    loop.call_soon_threadsafe(
                        lambda: status_queue.put_nowait(("error", str(e)))
                    )
                except Exception:
                    pass

    async def poll_script_status():
        nonlocal total_lines, last_line_id
        while is_running:
            try:
                await asyncio.sleep(1.0)
                if not is_running:
                    break

                current_script = get_script(script_id)
                if not current_script:
                    break

                new_status = current_script.get("status", "pending")
                new_lines = get_script_lines(script_id)
                new_total = len(new_lines)

                if new_total > total_lines:
                    added = [l for l in new_lines if l["id"] > last_line_id]
                    if added:
                        last_line_id = max(l["id"] for l in added)
                        total_lines = new_total
                        await line_queue.put(added)

                task_id = current_script.get("task_id", "")
                progress = 0
                message = ""
                if task_id:
                    task = agent_task_manager.get_task(task_id)
                    if task:
                        progress = task.get("progress", 0)
                        message = task.get("message", "")

                await _safe_send_json(websocket, {
                    "type": "status",
                    "status": new_status,
                    "progress": progress,
                    "message": message,
                    "total_lines": total_lines,
                })

                if new_status == "ready":
                    await status_queue.put(("finish", "full_script"))
                    break
                elif new_status == "failed":
                    await status_queue.put(("error", message or "剧本生成失败"))
                    break

            except Exception as e:
                add_log(f"[WebSocket-Script] 轮询异常: {e}", "WARNING")
                await asyncio.sleep(2.0)

    if current_status == "pending":
        add_log(f"[WebSocket-Script] 启动剧本生成任务")
        generate_task = asyncio.create_task(generate_script_task())
    elif current_status == "running":
        add_log(f"[WebSocket-Script] 剧本正在生成中，轮询等待更新...")
        generate_task = asyncio.create_task(poll_script_status())

    try:
        async def receive_loop():
            nonlocal generate_task, is_running
            while True:
                try:
                    data = await websocket.receive_text()
                    message = json.loads(data)
                    msg_type = message.get("type")
                    add_log(f"[WebSocket-Script] 收到消息: {msg_type}")
                    if msg_type == "ping":
                        await _safe_send_json(websocket, {"type": "pong"})
                    elif msg_type == "close":
                        break
                    elif msg_type == "stop_generation":
                        add_log(f"[WebSocket-Script] 用户请求停止生成")
                        is_running = False
                        service.stop_generation(script_id)
                        if generate_task and not generate_task.done():
                            generate_task.cancel()
                        await _safe_send_json(websocket, {
                            "type": "status",
                            "status": "ready",
                            "progress": 100,
                            "message": "生成已停止",
                            "total_lines": total_lines,
                        })
                        await _safe_send_json(websocket, {
                            "type": "finish",
                            "total_lines": total_lines,
                            "scope": "stopped",
                        })
                    elif msg_type == "generate_chapter":
                        chapter_index = message.get("chapter_index", 0)
                        add_log(f"[WebSocket-Script] 开始生成章节{chapter_index}")
                        is_running = True
                        if generate_task and not generate_task.done():
                            generate_task.cancel()
                        generate_task = asyncio.create_task(generate_chapter_task(chapter_index))
                        await _safe_send_json(websocket, {
                            "type": "status",
                            "status": "running",
                            "progress": 0,
                            "message": f"正在生成第 {chapter_index} 章台词",
                            "total_lines": total_lines,
                            "chapter_index": chapter_index,
                        })
                except WebSocketDisconnect:
                    break
                except Exception:
                    break

        async def send_loop():
            nonlocal total_lines
            while True:
                try:
                    try:
                        new_lines = await asyncio.wait_for(line_queue.get(), timeout=0.1)
                        if not is_running:
                            continue
                        total_lines += len(new_lines)
                        chapter_index = new_lines[0].get("chapter_index", 0) if new_lines else 0
                        await _safe_send_json(websocket, {
                            "type": "lines_added",
                            "lines": new_lines,
                            "chapter_index": chapter_index,
                        })
                        continue
                    except asyncio.TimeoutError:
                        pass

                    try:
                        status_type, msg = await asyncio.wait_for(status_queue.get(), timeout=0.01)
                        if status_type == "finish":
                            await _safe_send_json(websocket, {
                                "type": "finish",
                                "total_lines": total_lines,
                                "scope": msg or "",
                            })
                            continue
                        elif status_type == "error":
                            await _safe_send_json(websocket, {
                                "type": "error",
                                "message": msg or "剧本生成失败",
                            })
                            continue
                        continue
                    except asyncio.TimeoutError:
                        pass

                except WebSocketDisconnect:
                    break
                except Exception:
                    break

        receive_task = asyncio.create_task(receive_loop())
        send_task = asyncio.create_task(send_loop())

        done, pending = await asyncio.wait(
            [receive_task, send_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        add_log("[WebSocket-Script] 连接断开")
    except Exception as e:
        add_log(f"[WebSocket-Script] 异常: {e}", "ERROR")
        import traceback
        add_log(traceback.format_exc(), "ERROR")
    finally:
        is_running = False
        service.unregister_listener(script_id, listener_id)
        ws_broadcast_manager.unregister_connection(script_id, websocket)
        if current_status == "pending":
            if generate_task and not generate_task.done():
                generate_task.cancel()
        add_log("[WebSocket-Script] 连接关闭")
