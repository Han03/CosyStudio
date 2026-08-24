import os
import time
import json
import asyncio
import torch
import numpy as np

from utils.logger import logger
from core.global_manager import global_manager
from infrastructure.param_resolver import get_effective_params
from services.vector_store import search


def _get_qwen_model():
    return global_manager.qwen_model


def _get_cosyvoice_model():
    return global_manager.cosyvoice_model


def add_log(message: str, level: str = "INFO"):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    try:
        if level == "INFO":
            logger.info(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "ERROR":
            logger.error(message)
        else:
            logger.info(message)
    except:
        pass
    print(f"[LOG][{level}] {message}")


def _build_agent_description(agent):
    agent_description = ""
    if agent.get("name"):
        agent_description += f"角色名称: {agent['name']}\n"
    if agent.get("description"):
        agent_description += f"角色描述: {agent['description']}\n"
    if agent.get("prompt"):
        agent_description += f"角色提示: {agent['prompt']}\n"
    if agent.get("prompt_path"):
        try:
            with open(agent["prompt_path"], "r", encoding="utf-8") as f:
                prompt_content = f.read().strip()
                if prompt_content:
                    agent_description += f"角色提示词: {prompt_content}\n"
        except Exception:
            pass
    return agent_description

# ============================================================
#文本分析（Qwen 流式文本 + 可选 CosyVoice 朗读）
# ============================================================
async def handle_text_chat_response(websocket, agent, user_message, agent_description=None, session=None):
    """文本沟通：使用 ModelExecutor 进行文本预测 """
    from core.model_executor import model_executor

    if agent_description is None:
        agent_description = _build_agent_description(agent)

    from domain.prompts import process_user_message, process_response
    processed_text = process_user_message(user_message)

    add_log(f"[文本沟通] 用户消息: '{user_message[:30]}...', 处理后: '{processed_text[:30]}'")

    await websocket.send_json({"type": "stream_start", "message": "智能体正在回复..."})

    qwen_params = get_effective_params(agent, "qwen")

    full_text = ""

    async for chunk in model_executor.execute_text_predict(
        processed_text,
        system_prompt=agent_description.strip() if agent_description else "",
        stream=True,
        generate_params=qwen_params
    ):
        if chunk.get("type") == "text":
            content = chunk.get("content", "")
            full_text += content
            await websocket.send_json({"type": "stream_chunk", "content": content})
            await asyncio.sleep(0)
        elif chunk.get("type") == "finish":
            break
        elif chunk.get("error"):
            await websocket.send_json({"type": "error", "message": chunk["error"]})
            return ""

    await websocket.send_json({"type": "stream_finish"})
    add_log(f"[文本沟通] 回复生成完成: '{full_text[:1000]}...'")

    processed_response = process_response(full_text)
    await websocket.send_json({
        "type": "response",
        "text": processed_response,
        "audio_path": None
    })

    # 保存到会话历史
    if session and full_text:
        session.add_user_message(user_message)
        session.add_assistant_message(processed_response)
        add_log(f"[文本沟通] 已存入会话历史，当前历史轮数: {len(session.get_history()) // 2}")

    return full_text


async def send_text_chat_welcome(websocket, agent):
    """文本沟通欢迎消息：使用 ModelExecutor 生成欢迎文本 """
    from core.model_executor import model_executor
    try:
        await asyncio.sleep(0.5)

        agent_description = _build_agent_description(agent)
        if not agent_description.strip():
            add_log("智能体没有描述信息，跳过欢迎消息", "WARNING")
            return

        add_log("[文本沟通] 开始生成欢迎消息...")

        from domain.prompts import get_welcome_prompt, process_response
        welcome_prompt = get_welcome_prompt(agent_description.strip())

        await websocket.send_json({"type": "stream_start", "message": "智能体正在回复..."})

        generate_params = get_effective_params(agent, "qwen")

        full_text = ""
        async for chunk in model_executor.execute_text_predict(
            "",
            system_prompt=welcome_prompt,
            stream=False,
            generate_params=generate_params
        ):
            if chunk.get("type") == "text":
                full_text += chunk.get("content", "")
            elif chunk.get("error"):
                add_log(f"[文本沟通] 欢迎消息生成失败: {chunk['error']}", "WARNING")
                return

        full_text = process_response(full_text)

        await websocket.send_json({"type": "stream_chunk", "content": full_text})
        await websocket.send_json({"type": "stream_finish"})
        add_log(f"[文本沟通] 欢迎消息生成完成: '{full_text}'")

        await websocket.send_json({
            "type": "response",
            "text": full_text,
            "audio_path": None
        })

    except Exception as e:
        add_log(f"[文本沟通] 欢迎消息生成异常: {e}", "ERROR")
        import traceback
        add_log(traceback.format_exc(), "ERROR")


# 全局生成中断事件（用于打断/抢话）
_generation_stop_event = None
_current_generation_lock = None


def get_generation_stop_event():
    """获取当前生成的停止事件（用于打断）"""
    global _generation_stop_event, _current_generation_lock
    if _generation_stop_event is None:
        import asyncio
        _generation_stop_event = asyncio.Event()
        _current_generation_lock = asyncio.Lock()
    return _generation_stop_event


# ============================================================
# 文本朗读（CosyVoice TTS：输入文本，输出 PCM 音频流）
# ============================================================

async def handle_read_aloud_response(websocket, agent, text):
    """文本朗读：使用 ModelExecutor 进行语音合成"""
    import base64
    from core.model_executor import model_executor

    if not text or not text.strip():
        await websocket.send_json({"type": "error", "message": "文本内容为空"})
        return

    add_log(f"[文本朗读] 开始朗读: '{text[:50]}...'")

    await websocket.send_json({"type": "stream_start", "message": "正在合成语音..."})

    agent_id = agent.get("id")

    try:
        chunk_count = 0
        async for audio_chunk in model_executor.execute_text_to_speech(
            text, stream=True, agent_id=agent_id, tone=""
        ):
            if audio_chunk.get("type") == "pcm_chunk":
                sample_rate = audio_chunk.get("sample_rate")
                pcm_b64 = audio_chunk.get("data", "")
                pcm_bytes = base64.b64decode(pcm_b64)

                try:
                    header = json.dumps({
                        "type": "pcm_chunk",
                        "sample_rate": sample_rate
                    }).encode('utf-8')
                    message = b'\x00' + header + b'\x00' + pcm_bytes
                    await websocket.send_bytes(message)
                    chunk_count += 1
                except Exception as e:
                    add_log(f"[文本朗读] 发送PCM数据失败: {e}", "WARNING")
                    break
            elif audio_chunk.get("type") == "finish":
                try:
                    await websocket.send_json({"type": "pcm_finish"})
                except Exception:
                    pass
                add_log(f"[文本朗读] PCM合成完成，共发送 {chunk_count} 个音频块")
                break
            elif audio_chunk.get("type") == "error":
                add_log(f"[文本朗读] 合成失败: {audio_chunk.get('message')}", "WARNING")
                await websocket.send_json({"type": "error", "message": audio_chunk.get("message", "合成失败")})
                break

        await websocket.send_json({"type": "stream_finish"})
        await websocket.send_json({"type": "finish"})

    except Exception as e:
        add_log(f"[文本朗读] 异常: {e}", "ERROR")
        import traceback
        add_log(traceback.format_exc(), "ERROR")
        await websocket.send_json({"type": "error", "message": f"朗读失败: {str(e)}"})



