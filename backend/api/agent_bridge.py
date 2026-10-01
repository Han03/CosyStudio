"""CosyAgent 能力接入适配层（agent_bridge）。

将 CosyStudio 的长任务（整章合成/章节生成/电子书导入/ASR/角色对话）
统一为「提交 → 轮询状态 → 取结果」三步协议，供 CosyAgent 能力注册中心
以 endpointMode=submit-poll 方式调用。不改动任何现有业务代码。

端点：
  POST /agent-bridge/tasks             提交长任务 -> {task_id, status}
  GET  /agent-bridge/tasks/{id}        轮询状态 + 进度
  GET  /agent-bridge/tasks/{id}/result 成功后的完整结果
  GET  /agent-bridge/healthz           探活（CP probe 用）

安全：环境变量 COSY_AGENT_BRIDGE_TOKEN 设置后，所有端点校验
X-Capability-Token 请求头；未设置则放行（本地单机场景）。
"""
import asyncio
import hashlib
import json
import os
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException

from utils.logger import log_manager

router = APIRouter()
_logger = log_manager.get_logger("agent_bridge")

# ---------------- 任务存储（内存；重启丢失可接受） ----------------
_TASKS: Dict[str, Dict[str, Any]] = {}
_LOCK = asyncio.Lock()
_TOKEN = os.environ.get("COSY_AGENT_BRIDGE_TOKEN", "").strip()

# 幂等键 -> task_id（防止 Agent 重试导致重复合成/生成）
_IDEMPOTENT_KEY_TO_ID: Dict[str, str] = {}
# 不幂等的任务类型（对话类每次独立）
_NON_IDEMPOTENT = {"chat_complete"}


def _check_token(x_capability_token: Optional[str]) -> None:
    if _TOKEN and x_capability_token != _TOKEN:
        raise HTTPException(status_code=403, detail="invalid capability token")


def _idempotency_key(task_type: str, params: Dict[str, Any]) -> str:
    """重试危险类任务按 类型+关键参数 去重。"""
    if task_type in _NON_IDEMPOTENT:
        return ""
    if task_type == "chapter_tts":
        payload = (task_type, params.get("script_id"), params.get("chapter_index"))
    elif task_type == "script_generate":
        payload = (task_type, params.get("script_id"), params.get("chapter_index"))
    elif task_type in ("ebook_import", "asr"):
        payload = (task_type, params.get("path"))
    else:
        payload = (task_type, json.dumps(params, sort_keys=True))
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()


async def _submit(task_type: str, params: Dict[str, Any]) -> str:
    async with _LOCK:
        key = _idempotency_key(task_type, params)
        if key and key in _IDEMPOTENT_KEY_TO_ID:
            return _IDEMPOTENT_KEY_TO_ID[key]  # 幂等命中：返回既有任务
        task_id = uuid.uuid4().hex[:12]
        _TASKS[task_id] = {
            "task_id": task_id,
            "type": task_type,
            "status": "pending",
            "progress": 0,
            "params": params,
            "result": None,
            "error": None,
            "created_at": None,
            "updated_at": None,
        }
        if key:
            _IDEMPOTENT_KEY_TO_ID[key] = task_id
    asyncio.create_task(_run(task_id))
    return task_id


async def _set(task_id: str, **fields) -> None:
    async with _LOCK:
        if task_id in _TASKS:
            _TASKS[task_id].update(fields)


async def _run(task_id: str) -> None:
    t = _TASKS[task_id]
    try:
        await _set(task_id, status="running", progress=5)
        result = await _execute(t["type"], t["params"])
        await _set(task_id, status="success", progress=100, result=result)
        _logger.info(f"[agent_bridge] task {task_id} ({t['type']}) success")
    except HTTPException as e:
        await _set(task_id, status="failed", error=str(e.detail))
    except Exception as e:  # noqa: BLE001
        await _set(task_id, status="failed", error=f"{type(e).__name__}: {e}")
        _logger.error(f"[agent_bridge] task {task_id} failed: {e}")


# ---------------- 任务实现（壳层，复用现有 service） ----------------
async def _execute(task_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if task_type == "chapter_tts":
        # 整章合成：直接 await 现有路由处理函数（与 FastAPI 原生调用行为一致；
        # 内部为同步长循环，本地单机场景可接受）
        from api.audio_synthesize import synthesize_chapter_audio

        result = await synthesize_chapter_audio(
            script_id=params["script_id"], chapter_index=params["chapter_index"])
        return {"summary": "章节合成完成", "payload": result}

    if task_type == "script_generate":
        # 章节台词生成：await service 流式生成到完成
        from api.books import get_script_service

        service = get_script_service()
        result = await service.generate_chapter_script_stream(
            script_id=params["script_id"], chapter_index=params["chapter_index"])
        return {"summary": "章节台词生成完成", "payload": result}

    if task_type == "chat_complete":
        # 角色对话：SSE 聚合成完整文本
        from core.model_executor import model_executor

        text = params.get("text", "")
        agent_id = params.get("agent_id", "default")
        if not text:
            raise HTTPException(status_code=400, detail="缺少text字段")
        try:
            from api.agents import _get_agent
            agent = _get_agent(agent_id)
        except Exception:
            agent = None
        if not agent:
            agent = {"name": "默认助手", "description": "", "prompt": ""}
        system = f"你是{agent.get('name', '默认助手')}。{agent.get('description', '')}\n{agent.get('prompt', '')}"
        chunks = []
        async for chunk in model_executor.execute_text_predict(text, system, stream=True):
            if chunk.get("error"):
                raise HTTPException(status_code=502, detail=chunk["error"])
            content = chunk.get("content") or chunk.get("text") or ""
            if content:
                chunks.append(content)
        return {"summary": "对话完成", "text": "".join(chunks)}

    if task_type == "ebook_import":
        # 电子书导入：读本地文件 -> ingest（复用库服务）
        from api.books import get_ebook_library_service

        path = params.get("path", "")
        if not path or not os.path.isfile(path):
            raise HTTPException(status_code=400, detail=f"文件不存在: {path}")
        with open(path, "rb") as f:
            content = f.read()
        service = get_ebook_library_service()
        result = service.ingest(
            filename=os.path.basename(path),
            content=content,
            title=params.get("title"),
            author=params.get("author", ""),
            description=params.get("description", ""),
        )
        return {"summary": "电子书导入完成", "payload": result}

    if task_type == "asr":
        # 音频转写：复用 whisper 模型缓存与简繁转换
        from api.asr import _convert_to_simplified, get_whisper_model

        path = params.get("path", "")
        if not path or not os.path.isfile(path):
            raise HTTPException(status_code=400, detail=f"文件不存在: {path}")
        model = get_whisper_model(params.get("whisper_model", "base"))
        options = {}
        if params.get("language"):
            options["language"] = params["language"]
        elif params.get("force_simplified", True):
            options["language"] = "zh"
        if params.get("force_simplified", True) and options.get("language", "zh") == "zh":
            options["initial_prompt"] = (
                "以下是普通话的简体中文转写。使用简体汉字。"
            )
        result = await asyncio.to_thread(model.transcribe, path, **options)
        text = result.get("text", "").strip()
        if params.get("force_simplified", True):
            text = _convert_to_simplified(text)
        return {
            "summary": "音频转写完成",
            "text": text,
            "language": result.get("language", params.get("language", "")),
            "duration": result.get("duration", 0),
        }

    raise HTTPException(status_code=400, detail=f"未知任务类型: {task_type}")


# ---------------- 端点 ----------------
@router.post("/agent-bridge/tasks")
async def submit_task(request_body: Dict[str, Any],
                      x_capability_token: Optional[str] = Header(None)):
    _check_token(x_capability_token)
    task_type = request_body.get("type", "")
    params = request_body.get("params", {}) or {}
    if not task_type:
        raise HTTPException(status_code=400, detail="缺少type字段")
    task_id = await _submit(task_type, params)
    return {"task_id": task_id, "status": _TASKS[task_id]["status"]}


@router.get("/agent-bridge/tasks/{task_id}")
async def get_task(task_id: str,
                   x_capability_token: Optional[str] = Header(None)):
    _check_token(x_capability_token)
    t = _TASKS.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="task not found")
    return {
        "task_id": task_id,
        "type": t["type"],
        "status": t["status"],
        "progress": t["progress"],
        "error": t["error"],
        "result_summary": (t["result"] or {}).get("summary") if t["result"] else None,
    }


@router.get("/agent-bridge/tasks/{task_id}/result")
async def get_task_result(task_id: str,
                          x_capability_token: Optional[str] = Header(None)):
    _check_token(x_capability_token)
    t = _TASKS.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="task not found")
    if t["status"] != "success":
        raise HTTPException(status_code=409, detail=f"task 未完成: {t['status']}")
    return t["result"]


@router.get("/agent-bridge/healthz")
async def healthz():
    return {"status": "UP"}
