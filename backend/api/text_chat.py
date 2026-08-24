import os
import json
import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from utils.logger import logger
from core.global_manager import global_manager
from core.model_executor import ModelExecutor

router = APIRouter()

from core.paths import AGENTS_DATA_DIR


def add_log(message: str, level: str = "INFO"):
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


def _ensure_agent_manager():
    if global_manager.agent_manager is None:
        from agents.agent_manager import AgentManager
        global_manager.agent_manager = AgentManager(AGENTS_DATA_DIR)
    return global_manager.agent_manager


def _get_agent(agent_id):
    """根据 agent_id 获取智能体信息，不存在返回 None"""
    try:
        mgr = _ensure_agent_manager()
        return mgr.get_agent(agent_id)
    except Exception as e:
        add_log(f"获取智能体失败: {e}", "WARNING")
        return None


def _build_agent_description(agent):
    agent_description = ""
    if agent.get("name"):
        agent_description += f"角色名称: {agent['name']}\n"
    if agent.get("description"):
        agent_description += f"角色描述: {agent['description']}\n"
    if agent.get("prompt"):
        agent_description += f"角色提示: {agent['prompt']}\n"
    return agent_description

@router.post("/api/text/chat_stream")
async def chat_stream(request: Request):
    """流式文本对话（SSE 风格，每行一个 JSON）"""
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"请求体解析失败: {str(e)}")

    text = data.get("text", "")
    agent_id = data.get("agent_id", "default")

    if not text:
        raise HTTPException(status_code=400, detail="缺少text字段")

    agent = _get_agent(agent_id)
    if agent is None:
        agent = {"name": "默认助手", "description": "", "prompt": ""}

    agent_description = _build_agent_description(agent)

    executor = ModelExecutor()

    async def generate():
        async for chunk in executor.execute_text_predict(text, agent_description, stream=True):
            if chunk.get("error"):
                yield json.dumps({"type": "error", "content": chunk["error"]}).encode() + b"\n"
                break
            yield json.dumps(chunk).encode() + b"\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
