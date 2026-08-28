import os
import json
import time
import asyncio
import base64
import numpy as np

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from utils.logger import logger
from core.model_executor import ModelExecutor
from services.audio_service import (
    add_log,
    synthesize_line_to_wav as _synthesize_line_to_wav,
    format_srt_timestamp as _format_srt_timestamp,
    build_srt as _build_srt,
    merge_wav_segments,
)

router = APIRouter()

from core.paths import AGENTS_DATA_DIR


def _resolve_tts_params(config: dict, line_seed: int = 0) -> dict:
    """从角色配置中解析 TTS 参数。
    
    返回 dict:
    - is_cloud: bool
    - agent_id: str
    - seed: int
    - capability_id: str | None
    - extra_params: dict | None
    """
    tts_cap_id = config.get("tts_capability_id", "")
    cloud_extra_raw = config.get("cloud_extra_params", "{}")
    agent_id = config.get("agent_id", "")
    seed = int(config.get("seed", 0))

    # 解析云端额外参数
    extra_params = None
    if cloud_extra_raw:
        try:
            extra_params = json.loads(cloud_extra_raw) if isinstance(cloud_extra_raw, str) else cloud_extra_raw
        except (json.JSONDecodeError, TypeError):
            extra_params = None

    # 判断是否使用云端能力
    is_cloud = False
    capability_id = None
    if tts_cap_id:
        from core.model_executor import model_executor
        if model_executor.is_cloud_capability(tts_cap_id):
            is_cloud = True
            capability_id = tts_cap_id

    if not is_cloud:
        # 本地模式：使用 agent_id
        capability_id = None
        extra_params = None
        seed = line_seed if line_seed != 0 else seed

    return {
        "is_cloud": is_cloud,
        "agent_id": agent_id,
        "seed": seed,
        "capability_id": capability_id,
        "extra_params": extra_params,
    }

@router.post("/api/audio/synthesize")
async def synthesize_audio(request: Request):
    """文本合成语音 - 流式输出 PCM 音频

    请求体:
    - text: 要合成的文本
    - agent_id: 智能体ID
    - seed: 随机种子
    - instruction: 语气指令（自然语言，如"请非常开心地说一句话"，仅 CosyVoice3 生效）
    - tone: 语气名称

    返回 NDJSON 流（每行一个 JSON 对象）：
    - {"type":"start","sample_rate":24000,"agent_id":"...","text":"..."}
    - {"type":"pcm_chunk","sample_rate":24000,"chunk_index":0,"data":"<base64 int16 PCM>"}
    - {"type":"finish","sample_rate":24000,"chunk_count":N}
    - {"type":"error","message":"..."}
    """
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"请求体解析失败: {str(e)}")

    text = data.get("text", "")
    agent_id = data.get("agent_id", "default")
    seed = data.get("seed", 0)
    instruction = data.get("instruction", "")
    tone = data.get("tone", "")

    if not text:
        raise HTTPException(status_code=400, detail="缺少text字段")

    add_log(f"[文本合成] 流式合成语音: '{text[:30]}...', agent={agent_id}, seed={seed}, tone={tone}, instruction={instruction}")

    executor = ModelExecutor()

    async def generate():
        chunk_count = 0
        try:
            async for chunk in executor.execute_text_to_speech(
                text,
                stream=True,
                agent_id=agent_id,
                tone=tone,
                instruction=instruction,
                seed=seed
            ):
                if chunk.get("error"):
                    yield (json.dumps({"type": "error", "message": chunk["error"]}) + "\n").encode("utf-8")
                    break
                yield (json.dumps(chunk) + "\n").encode("utf-8")
                if chunk.get("type") == "pcm_chunk":
                    chunk_count += 1
                elif chunk.get("type") == "finish":
                    add_log(f"[文本合成] 流式合成完成，共 {chunk_count} 个音频块")
                    break
        except Exception as e:
            add_log(f"[文本合成] 流式合成异常: {e}", "ERROR")
            import traceback
            add_log(traceback.format_exc(), "ERROR")
            yield (json.dumps({"type": "error", "message": str(e)}) + "\n").encode("utf-8")

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.post("/api/audio/generate-and-save")
async def generate_and_save_audio(line_id: int):
    """根据台词ID生成语音，并保存到媒体管理器中。
    
    自动从数据库获取语句的文本、角色、语气，并查询该角色的配音配置，
    调用 CosyVoice 生成语音后：
    1. 将音频保存为 WAV 文件到媒体管理器
    2. 更新 script_lines 表的 audio_path 字段
    3. 返回流式音频供前端试听

    返回 NDJSON 流：
    - {"type":"start","sample_rate":24000,"line_id":...,"role":"...","text":"..."}
    - {"type":"pcm_chunk","sample_rate":24000,"chunk_index":0,"data":"<base64 int16 PCM>"}
    - {"type":"finish","sample_rate":24000,"chunk_count":N,"audio_path":"..."}
    - {"type":"error","message":"..."}
    """
    from core.global_manager import global_manager
    from core.model_executor import ModelExecutor

    if global_manager.is_model_busy():
        raise HTTPException(status_code=400, detail="系统繁忙，请稍后再试")

    if not global_manager.try_acquire_model("cosyvoice"):
        raise HTTPException(status_code=400, detail="系统繁忙，请稍后再试")

    try:
        from repositories import get_script_line_by_id, get_character_config
        from services.media_manager import get_media_manager

        line = get_script_line_by_id(line_id)
        if not line:
            global_manager.release_model()
            raise HTTPException(status_code=404, detail=f"台词 {line_id} 不存在")

        text = line.get("content", "")
        role = line.get("role", "")
        instruction = line.get("instruction", "")
        tone = line.get("tone", "")
        script_id = line.get("script_id")
        line_seed = int(line.get("seed", 0))

        if not text:
            global_manager.release_model()
            raise HTTPException(status_code=400, detail="语句内容为空")

        config = get_character_config(script_id, role) if script_id and role else None
        if not config:
            config = {"agent_id": "", "speed": 1.0, "seed": 0}

        tts = _resolve_tts_params(config, line_seed)
        agent_id = tts["agent_id"]
        seed = tts["seed"]
        # config 中的原始 tts_capability_id（保留本地能力的实际 ID），用于保存和匹配音频历史
        config_tts_cap_id = config.get("tts_capability_id", "") or ""

        if not tts["is_cloud"] and not agent_id:
            global_manager.release_model()
            raise HTTPException(
                status_code=400,
                detail=f"角色「{role}」尚未配置配音智能体或云端能力，请先在角色设置中选择",
            )

        add_log(
            f"[语音生成保存] line_id={line_id}, role='{role}', tone='{tone}', instruction='{instruction}', "
            f"agent={tts['agent_id']}, cloud={tts['is_cloud']}, cap={tts['capability_id']}, text='{text[:30]}...'"
        )

        try:
            from infrastructure.websocket_broadcast import ws_broadcast_manager
            if script_id:
                asyncio.create_task(ws_broadcast_manager.broadcast_line_generating(script_id, line_id))
        except Exception as e:
            add_log(f"[语音生成保存] WebSocket通知失败: {e}", "WARNING")

        executor = ModelExecutor()
        
        async def generate():
            sample_rate = None
            chunk_count = 0
            audio_data_list = []
            
            try:
                yield (json.dumps({
                    "type": "start",
                    "line_id": line_id,
                    "role": role,
                    "text": text[:200],
                }) + "\n").encode("utf-8")

                async for audio_chunk in executor.execute_text_to_speech(
                    text, stream=True, capability_id=tts["capability_id"],
                    agent_id=tts["agent_id"], tone=tone, instruction=instruction,
                    seed=tts["seed"], extra_params=tts["extra_params"]
                ):
                    if audio_chunk.get("type") == "pcm_chunk":
                        sample_rate = audio_chunk["sample_rate"]
                        pcm_b64 = audio_chunk["data"]
                        pcm_bytes = base64.b64decode(pcm_b64)
                        audio_data_list.append(pcm_bytes)
                        
                        msg = {
                            "type": "pcm_chunk",
                            "sample_rate": sample_rate,
                            "chunk_index": chunk_count,
                            "data": pcm_b64,
                        }
                        yield (json.dumps(msg) + "\n").encode("utf-8")
                        chunk_count += 1
                    elif audio_chunk.get("type") == "finish":
                        if audio_data_list and sample_rate:
                            import wave
                            from io import BytesIO
                            
                            all_audio_data = b"".join(audio_data_list)
                            
                            wav_buffer = BytesIO()
                            with wave.open(wav_buffer, "wb") as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(sample_rate)
                                wf.writeframes(all_audio_data)
                            
                            wav_buffer.seek(0)
                            wav_data = wav_buffer.read()
                            
                            media_mgr = get_media_manager()
                            filename = f"script_line_{line_id}_{int(time.time())}.wav"
                            audio_path = media_mgr.save_file(
                                module="tts",
                                filename=filename,
                                content=wav_data,
                                category="audio"
                            )
                            
                            from repositories import save_audio_history, get_script_line_by_id
                            save_audio_history(line_id, text, role, tone, instruction, agent_id, seed, audio_path, tts_capability_id=config_tts_cap_id)
                            
                            add_log(f"[语音生成保存] 音频已保存: {audio_path}")

                            try:
                                line_info = get_script_line_by_id(line_id)
                                if line_info:
                                    script_id = line_info.get("script_id")
                                    if script_id:
                                        from infrastructure.websocket_broadcast import ws_broadcast_manager
                                        asyncio.create_task(ws_broadcast_manager.broadcast_audio_generated(script_id, line_id))
                            except Exception as e:
                                add_log(f"[语音生成保存] WebSocket通知失败: {e}", "WARNING")
                        else:
                            audio_path = ""
                            
                        msg = {
                            "type": "finish",
                            "sample_rate": sample_rate,
                            "chunk_count": chunk_count,
                            "audio_path": audio_path,
                        }
                        yield (json.dumps(msg) + "\n").encode("utf-8")
                        add_log(f"[语音生成保存] 合成完成，line_id={line_id}, {chunk_count} 个音频块")
                    elif audio_chunk.get("type") == "error":
                        msg = {"type": "error", "message": audio_chunk.get("message", "合成失败")}
                        yield (json.dumps(msg) + "\n").encode("utf-8")
                        add_log(f"[语音生成保存] 合成失败: {audio_chunk.get('message')}", "WARNING")
                        break
            except Exception as e:
                add_log(f"[语音生成保存] 流式合成异常: {e}", "ERROR")
                import traceback
                add_log(traceback.format_exc(), "ERROR")
                msg = {"type": "error", "message": str(e)}
                yield (json.dumps(msg) + "\n").encode("utf-8")
            finally:
                global_manager.release_model()

        return StreamingResponse(generate(), media_type="application/x-ndjson")

    except HTTPException:
        raise
    except Exception as e:
        global_manager.release_model()
        raise


@router.get("/api/audio/history")
async def get_audio_history(line_id: int):
    """获取指定台词的语音生成历史记录。"""
    from repositories import get_audio_history_by_line_id, get_script_line_by_id

    line = get_script_line_by_id(line_id)
    if not line:
        raise HTTPException(status_code=404, detail=f"台词 {line_id} 不存在")

    history = get_audio_history_by_line_id(line_id)
    return {"success": True, "history": history}


@router.post("/api/audio/history/batch-match")
async def batch_match_audio_history(request: Request):
    """批量匹配多条语句的音频历史记录。
    
    请求体: {"lines": [{"line_id": int, "content": str, "role": str, "tone": str, "instruction": str, "agent_id": str, "tts_capability_id": str, "seed": int}, ...]}
    返回: {"success": True, "matches": {"line_id": {"audio_path": str, "audio_volume": float, "audio_pitch": int, "fade_in": float, "fade_out": float, "audio_adjust_enabled": int, "range_start": float, "range_end": float} | null}}
    """
    from repositories import get_matching_audio_history

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体解析失败")

    lines = data.get("lines", [])
    matches = {}

    for item in lines:
        line_id = item.get("line_id")
        if not line_id:
            continue
        content = item.get("content", "")
        role = item.get("role", "")
        tone = item.get("tone", "")
        instruction = item.get("instruction", "")
        agent_id = item.get("agent_id", "")
        tts_capability_id = item.get("tts_capability_id", "")
        seed = int(item.get("seed", 0))

        matched = get_matching_audio_history(line_id, content, role, tone, instruction, agent_id, seed, tts_capability_id=tts_capability_id)
        if matched:
            matches[line_id] = {
                "audio_path": matched.get("audio_path", ""),
                "audio_volume": matched.get("audio_volume", 1.0),
                "audio_pitch": matched.get("audio_pitch", 0),
                "fade_in": matched.get("fade_in", 0.0),
                "fade_out": matched.get("fade_out", 0.0),
                "audio_adjust_enabled": matched.get("audio_adjust_enabled", 0),
                "range_start": matched.get("range_start", 0.0),
                "range_end": matched.get("range_end", 0.0),
            }
        else:
            matches[line_id] = None

    return {"success": True, "matches": matches}


@router.post("/api/audio/reload-history")
async def reload_audio_history(history_id: int):
    """重新加载历史配置，将历史记录应用到当前语句。
    
    将指定历史记录的 audio_path 设置为当前语句的匹配音频。
    实际上就是返回该历史记录的音频路径供前端使用。
    """
    from repositories import get_audio_history_by_id

    target = get_audio_history_by_id(history_id)
    if not target:
        raise HTTPException(status_code=404, detail=f"历史记录 {history_id} 不存在")

    return {
        "success": True,
        "audio_path": target["audio_path"],
        "content": target["content"],
        "role": target["role"],
        "tone": target["tone"],
        "instruction": target["instruction"],
        "agent_id": target["agent_id"],
        "seed": target["seed"],
    }


@router.post("/api/audio/save-audio-settings")
async def save_audio_settings(line_id: int, request: Request):
    """保存语句的音频编辑参数（参数绑定到当前匹配的音频历史记录）。"""
    try:
        settings = await request.json()
    except Exception:
        settings = {}
    volume = float(settings.get("volume", 100)) / 100.0
    pitch = int(settings.get("pitch", 0))
    fade_in = float(settings.get("fade_in", 0.0))
    fade_out = float(settings.get("fade_out", 0.0))
    audio_adjust_enabled = int(settings.get("audio_adjust_enabled", 0))
    range_start = float(settings.get("range_start", 0.0))
    range_end = float(settings.get("range_end", 0.0))

    # 查询台词数据，计算 8 字段匹配条件，确保更新的是前端当前使用的音频记录
    from repositories import get_script_line_by_id, get_character_config
    line = get_script_line_by_id(line_id)
    if not line:
        raise HTTPException(status_code=404, detail=f"台词 {line_id} 不存在")

    content = line.get("content", "")
    role = line.get("role", "")
    tone = line.get("tone", "")
    instruction = line.get("instruction", "")
    script_id = line.get("script_id")

    config = get_character_config(script_id, role) if script_id and role else {}
    agent_id = config.get("agent_id", "") or ""
    tts_capability_id = config.get("tts_capability_id", "") or ""

    # effective_seed 与前端 batch-match 及 play-line 保持一致
    line_seed = int(line.get("seed", 0))
    effective_seed = line_seed if line_seed != 0 else int(config.get("seed", 0))

    from repositories.audio_history_repository import update_matching_audio_history_params
    update_matching_audio_history_params(
        line_id, content, role, tone, instruction, agent_id, effective_seed, tts_capability_id,
        volume, pitch, fade_in, fade_out, audio_adjust_enabled, range_start, range_end
    )

    add_log(f"[音频设置保存] line_id={line_id}, volume={volume}, pitch={pitch}, fade_in={fade_in}, fade_out={fade_out}, audio_adjust_enabled={audio_adjust_enabled}, range_start={range_start}, range_end={range_end}")
    return {"success": True, "message": "音频设置保存成功"}


@router.post("/api/audio/play-with-settings")
async def play_with_settings(line_id: int, request: Request):
    """根据语句ID和保存的音频参数播放语音。
    
    优先使用已存在的音频文件进行带参数播放（不需要模型锁），
    仅在没有音频文件需要合成时才获取模型锁。
    """
    from core.global_manager import global_manager

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    from repositories import get_script_line_by_id, get_character_config, get_matching_audio_history
    
    line = get_script_line_by_id(line_id)
    if not line:
        raise HTTPException(status_code=404, detail=f"台词 {line_id} 不存在")
    
    text = line.get("content", "")
    role = line.get("role", "")
    instruction = line.get("instruction", "")
    tone = line.get("tone", "")
    script_id = line.get("script_id")
    line_seed = int(line.get("seed", 0))

    config = get_character_config(script_id, role) if script_id and role else None
    if not config:
        config = {"agent_id": "", "speed": 1.0, "seed": 0}

    tts = _resolve_tts_params(config, line_seed)
    agent_id = tts["agent_id"]
    seed = tts["seed"]
    config_tts_cap_id = config.get("tts_capability_id", "") or ""
    tts_capability_id = config_tts_cap_id

    # 使用当前角色配置匹配音频历史（与前端 batch-match 一致）
    effective_seed = line_seed if line_seed != 0 else int(config.get("seed", 0))
    matched_history = get_matching_audio_history(line_id, text, role, tone, instruction, agent_id, effective_seed, tts_capability_id=tts_capability_id)
    audio_path = matched_history["audio_path"] if matched_history else ""

    # 从音频历史读取调整参数（参数绑定在音频上，script_line_audio_history 是权威数据源）
    volume = float(matched_history.get("audio_volume", 1.0)) if matched_history else 1.0
    pitch = int(matched_history.get("audio_pitch", 0)) if matched_history else 0
    fade_in = float(matched_history.get("fade_in", 0.0)) if matched_history else 0.0
    fade_out = float(matched_history.get("fade_out", 0.0)) if matched_history else 0.0
    audio_adjust_enabled = int(matched_history.get("audio_adjust_enabled", 0)) if matched_history else 0

    range_start = 0.0
    range_end = 0.0
    if audio_adjust_enabled:
        range_start = float(payload.get("range_start", 0.0))
        range_end = float(payload.get("range_end", 0.0))

    add_log(f"[带参数播放] line_id={line_id}, audio_path={audio_path}, audio_adjust_enabled={audio_adjust_enabled}, volume={volume}, pitch={pitch}, fade_in={fade_in}, fade_out={fade_out}, range=[{range_start},{range_end}]")

    # 分支1：已有音频文件，直接带参数流式返回（不需要模型锁）
    if audio_path:
        from services.media_manager import get_media_manager
        media_mgr = get_media_manager()
        file_info = media_mgr.get_file_by_path(audio_path)
        full_path = file_info["absolute_path"] if file_info else ""

        if full_path and os.path.exists(full_path):
            from services.audio_service import stream_wav_file_as_pcm

            async def generate_from_file():
                async for msg in stream_wav_file_as_pcm(
                    full_path,
                    volume=volume, pitch=pitch,
                    fade_in=fade_in, fade_out=fade_out,
                    range_start=range_start, range_end=range_end,
                    audio_adjust_enabled=audio_adjust_enabled,
                ):
                    if msg["type"] == "start":
                        msg["line_id"] = line_id
                    yield (json.dumps(msg) + "\n").encode("utf-8")

            return StreamingResponse(generate_from_file(), media_type="application/x-ndjson")

    # 分支2：没有音频文件，需要合成（需要模型锁）
    if global_manager.is_model_busy():
        raise HTTPException(status_code=400, detail="系统繁忙，请稍后再试")

    if not global_manager.try_acquire_model("cosyvoice"):
        raise HTTPException(status_code=400, detail="系统繁忙，请稍后再试")

    try:
        if not text:
            global_manager.release_model()
            raise HTTPException(status_code=400, detail="语句内容为空")

        if not tts["is_cloud"] and not agent_id:
            global_manager.release_model()
            raise HTTPException(
                status_code=400,
                detail=f"角色「{role}」尚未配置配音智能体或云端能力，请先在角色设置中选择",
            )
        
        executor = ModelExecutor()
        
        async def generate():
            sample_rate = None
            chunk_count = 0
            audio_data_list = []
            saved_audio_path = ""
        
            try:
                yield (json.dumps({
                    "type": "start",
                    "line_id": line_id,
                    "role": role,
                    "text": text[:200],
                }) + "\n").encode("utf-8")
        
                async for audio_chunk in executor.execute_text_to_speech(
                    text, stream=True, capability_id=tts["capability_id"],
                    agent_id=tts["agent_id"], tone=tone, instruction=instruction,
                    seed=tts["seed"], extra_params=tts["extra_params"]
                ):
                    if audio_chunk.get("type") == "pcm_chunk":
                        sample_rate = audio_chunk["sample_rate"]
                        pcm_b64 = audio_chunk["data"]
                        pcm_bytes = base64.b64decode(pcm_b64)
                        audio_data_list.append(pcm_bytes)

                        msg = {
                            "type": "pcm_chunk",
                            "sample_rate": sample_rate,
                            "chunk_index": chunk_count,
                            "data": pcm_b64,
                        }
                        yield (json.dumps(msg) + "\n").encode("utf-8")
                        chunk_count += 1
                    elif audio_chunk.get("type") == "finish":
                        if audio_data_list and sample_rate:
                            y = np.frombuffer(b"".join(audio_data_list), dtype=np.int16).astype(np.float32) / 32768.0

                            if audio_adjust_enabled:
                                y = y * volume

                                if fade_in > 0:
                                    fade_in_samples = min(int(fade_in * sample_rate), len(y))
                                    if fade_in_samples > 0:
                                        y[:fade_in_samples] *= np.linspace(0, 1, fade_in_samples)

                                if fade_out > 0:
                                    fade_out_samples = min(int(fade_out * sample_rate), len(y))
                                    if fade_out_samples > 0:
                                        y[-fade_out_samples:] *= np.linspace(1, 0, fade_out_samples)

                            y = np.clip(y, -1.0, 1.0)

                            from io import BytesIO
                            import wave as wave_module
                            wav_buffer = BytesIO()
                            with wave_module.open(wav_buffer, 'wb') as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(sample_rate)
                                wf.writeframes((y * 32767).astype(np.int16).tobytes())

                            wav_buffer.seek(0)
                            wav_data = wav_buffer.read()

                            media_mgr = get_media_manager()
                            filename = f"script_line_{line_id}_{int(time.time())}.wav"
                            saved_audio_path = media_mgr.save_file(
                                module="tts",
                                filename=filename,
                                content=wav_data,
                                category="audio"
                            )

                            from repositories import save_audio_history
                            save_audio_history(line_id, text, role, tone, instruction, agent_id, seed, saved_audio_path, tts_capability_id=config_tts_cap_id)

                        msg = {
                            "type": "finish",
                            "sample_rate": sample_rate,
                            "chunk_count": chunk_count,
                            "audio_path": saved_audio_path,
                        }
                        yield (json.dumps(msg) + "\n").encode("utf-8")
                        add_log(f"[带参数播放] 合成完成，line_id={line_id}, {chunk_count} 个音频块")
                    elif audio_chunk.get("type") == "error":
                        msg = {"type": "error", "message": audio_chunk.get("message", "合成失败")}
                        yield (json.dumps(msg) + "\n").encode("utf-8")
                        add_log(f"[带参数播放] 合成失败: {audio_chunk.get('message')}", "WARNING")
                        break
            except Exception as e:
                add_log(f"[带参数播放] 流式合成异常: {e}", "ERROR")
                import traceback
                add_log(traceback.format_exc(), "ERROR")
                msg = {"type": "error", "message": str(e)}
                yield (json.dumps(msg) + "\n").encode("utf-8")
            finally:
                global_manager.release_model()

        return StreamingResponse(generate(), media_type="application/x-ndjson")

    except HTTPException:
        raise
    except Exception as e:
        global_manager.release_model()
        raise


@router.post("/api/audio/play-line")
async def play_script_line(line_id: int):
    """根据台词ID流式播放语音（剧本编辑器整章播放专用）。

    优先使用已生成的音频文件（audio_path）；若不存在，则调用 CosyVoice 合成、
    保存为 WAV 文件并更新 audio_path，避免重复播放时重复合成。

    返回 NDJSON 流（每行一个 JSON 对象）：
    - {"type":"start","sample_rate":24000,"line_id":...,"role":"...","text":"..."}
    - {"type":"pcm_chunk","sample_rate":24000,"chunk_index":0,"data":"<base64 int16 PCM>"}
    - {"type":"finish","sample_rate":24000,"chunk_count":N,"audio_path":"..."}
    - {"type":"error","message":"..."}
    """
    from core.global_manager import global_manager

    if global_manager.is_model_busy():
        raise HTTPException(status_code=400, detail="系统繁忙，请稍后再试")

    if not global_manager.try_acquire_model("cosyvoice"):
        raise HTTPException(status_code=400, detail="系统繁忙，请稍后再试")

    try:
        from repositories import get_script_line_by_id, get_character_config, get_matching_audio_history, save_audio_history
        line = get_script_line_by_id(line_id)
        if not line:
            global_manager.release_model()
            raise HTTPException(status_code=404, detail=f"台词 {line_id} 不存在")

        text = line.get("content", "")
        role = line.get("role", "")
        script_id = line.get("script_id")
        instruction = line.get("instruction", "")
        tone = line.get("tone", "")

        config = get_character_config(script_id, role) if script_id and role else None
        if not config:
            config = {"agent_id": "", "speed": 1.0, "seed": 0}

        tts = _resolve_tts_params(config, int(line.get("seed", 0)))
        agent_id = tts["agent_id"]
        speed = float(config.get("speed", 1.0))
        seed = tts["seed"]

        config_tts_cap_id = config.get("tts_capability_id", "") or ""
        tts_capability_id = config_tts_cap_id

        # 使用当前角色配置匹配音频历史（与前端 batch-match 一致）
        effective_seed = int(line.get("seed", 0))
        if effective_seed == 0:
            effective_seed = int(config.get("seed", 0))
        matched_history = get_matching_audio_history(line_id, text, role, tone, instruction, agent_id, effective_seed, tts_capability_id=tts_capability_id)
        audio_path = matched_history["audio_path"] if matched_history else ""

        # 分支1：匹配到历史音频文件，直接从文件流式返回
        if audio_path:
            from services.media_manager import get_media_manager
            media_mgr = get_media_manager()
            file_info = media_mgr.get_file_by_path(audio_path)
            full_path = file_info["absolute_path"] if file_info else ""

            if full_path and os.path.exists(full_path):
                # 从音频历史读取调整参数（参数绑定在音频上，script_line_audio_history 是权威数据源）
                volume = float(matched_history.get("audio_volume", 1.0)) if matched_history else 1.0
                pitch = int(matched_history.get("audio_pitch", 0)) if matched_history else 0
                fade_in = float(matched_history.get("fade_in", 0.0)) if matched_history else 0.0
                fade_out = float(matched_history.get("fade_out", 0.0)) if matched_history else 0.0
                audio_adjust_enabled = int(matched_history.get("audio_adjust_enabled", 0)) if matched_history else 0
                range_start = float(matched_history.get("range_start", 0.0)) if matched_history else 0.0
                range_end = float(matched_history.get("range_end", 0.0)) if matched_history else 0.0

                add_log(f"[剧本播放] line_id={line_id} 从匹配的历史文件播放: {audio_path}, adjust={audio_adjust_enabled}, volume={volume}, pitch={pitch}")

                from services.audio_service import stream_wav_file_as_pcm

                async def generate_from_file():
                    try:
                        async for msg in stream_wav_file_as_pcm(
                            full_path,
                            volume=volume, pitch=pitch,
                            fade_in=fade_in, fade_out=fade_out,
                            range_start=range_start, range_end=range_end,
                            audio_adjust_enabled=audio_adjust_enabled,
                        ):
                            if msg["type"] == "start":
                                msg["line_id"] = line_id
                                msg["role"] = role
                                msg["text"] = text[:200]
                            elif msg["type"] == "finish":
                                msg["audio_path"] = audio_path
                            yield (json.dumps(msg) + "\n").encode("utf-8")
                    finally:
                        global_manager.release_model()

                return StreamingResponse(generate_from_file(), media_type="application/x-ndjson")

        # 分支2：未匹配到历史音频，合成并保存到历史记录
        if not text:
            global_manager.release_model()
            raise HTTPException(status_code=400, detail="语句内容为空")

        if not tts["is_cloud"] and not agent_id:
            global_manager.release_model()
            raise HTTPException(
                status_code=400,
                detail=f"角色「{role}」尚未配置配音智能体或云端能力，请先在角色设置中选择",
            )

        add_log(
            f"[剧本播放] line_id={line_id} 未匹配到历史音频，开始合成, role='{role}', tone='{tone}', "
            f"instruction='{instruction}', agent={agent_id}, cloud={tts['is_cloud']}, speed={speed}, seed={seed}, text='{text[:30]}...'"
        )

        try:
            from infrastructure.websocket_broadcast import ws_broadcast_manager
            if script_id:
                asyncio.create_task(ws_broadcast_manager.broadcast_line_generating(script_id, line_id))
        except Exception as e:
            add_log(f"[剧本播放] WebSocket通知失败: {e}", "WARNING")

        executor = ModelExecutor()

        async def generate_and_save():
            sample_rate = None
            chunk_count = 0
            audio_data_list = []
            saved_audio_path = ""
            try:
                yield (json.dumps({
                    "type": "start",
                    "line_id": line_id,
                    "role": role,
                    "text": text[:200],
                }) + "\n").encode("utf-8")

                async for audio_chunk in executor.execute_text_to_speech(
                    text, stream=True, capability_id=tts["capability_id"],
                    agent_id=tts["agent_id"], tone=tone, instruction=instruction,
                    seed=tts["seed"], extra_params=tts["extra_params"]
                ):
                    if audio_chunk.get("type") == "pcm_chunk":
                        sample_rate = audio_chunk["sample_rate"]
                        pcm_b64 = audio_chunk["data"]
                        pcm_bytes = base64.b64decode(pcm_b64)
                        audio_data_list.append(pcm_bytes)

                        yield (json.dumps({
                            "type": "pcm_chunk",
                            "sample_rate": sample_rate,
                            "chunk_index": chunk_count,
                            "data": pcm_b64,
                        }) + "\n").encode("utf-8")
                        chunk_count += 1
                    elif audio_chunk.get("type") == "finish":
                        # 保存为 WAV 文件并记录生成历史
                        if audio_data_list and sample_rate:
                            import wave
                            from io import BytesIO
                            all_audio_data = b"".join(audio_data_list)
                            wav_buffer = BytesIO()
                            with wave.open(wav_buffer, "wb") as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(sample_rate)
                                wf.writeframes(all_audio_data)
                            wav_buffer.seek(0)
                            wav_data = wav_buffer.read()

                            from services.media_manager import get_media_manager
                            media_mgr = get_media_manager()
                            filename = f"script_line_{line_id}_{int(time.time())}.wav"
                            saved_audio_path = media_mgr.save_file(
                                module="tts",
                                filename=filename,
                                content=wav_data,
                                category="audio"
                            )
                            save_audio_history(line_id, text, role, tone, instruction, agent_id, seed, saved_audio_path, tts_capability_id=config_tts_cap_id)

                            try:
                                from infrastructure.websocket_broadcast import ws_broadcast_manager
                                asyncio.create_task(ws_broadcast_manager.broadcast_audio_generated(script_id, line_id))
                            except Exception as e:
                                add_log(f"[剧本播放] WebSocket通知失败: {e}", "WARNING")
                            add_log(f"[剧本播放] 音频已保存到历史记录: {saved_audio_path}")

                        yield (json.dumps({
                            "type": "finish",
                            "sample_rate": sample_rate,
                            "chunk_count": chunk_count,
                            "audio_path": saved_audio_path,
                        }) + "\n").encode("utf-8")
                        add_log(f"[剧本播放] 合成完成，line_id={line_id}, {chunk_count} 个音频块")
                    elif audio_chunk.get("type") == "error":
                        yield (json.dumps({"type": "error", "message": audio_chunk.get("message", "合成失败")}) + "\n").encode("utf-8")
                        add_log(f"[剧本播放] 合成失败: {audio_chunk.get('message')}", "WARNING")
                        break
            except Exception as e:
                add_log(f"[剧本播放] 流式合成异常: {e}", "ERROR")
                import traceback
                add_log(traceback.format_exc(), "ERROR")
                yield (json.dumps({"type": "error", "message": str(e)}) + "\n").encode("utf-8")
            finally:
                global_manager.release_model()

        return StreamingResponse(generate_and_save(), media_type="application/x-ndjson")

    except HTTPException:
        raise
    except Exception as e:
        global_manager.release_model()
        raise


# _synthesize_line_to_wav, _format_srt_timestamp, _build_srt 已迁移到 services/audio_service.py


@router.post("/api/audio/export-chapter")
async def export_chapter_audio(script_id: int, chapter_index: int):
    """导出整章音频和 SRT 文稿。

    1. 获取章节所有语句
    2. 对没有 audio_path 的语句调用 CosyVoice 合成并保存为 WAV
    3. 合并所有语句的音频为一个完整 WAV
    4. 根据每条语句时长生成 SRT 文稿
    5. 打包为 ZIP（含两个文件：audio.wav, subtitles.srt）返回

    返回:
        ZIP 文件流，响应头 X-Export-Info 包含 audio_paths 信息（JSON）
    """
    from core.global_manager import global_manager

    if global_manager.is_model_busy():
        raise HTTPException(status_code=400, detail="系统繁忙，请稍后再试")

    if not global_manager.try_acquire_model("cosyvoice"):
        raise HTTPException(status_code=400, detail="系统繁忙，请稍后再试")

    try:
        from repositories import (
            get_script, get_script_lines, get_character_config,
            get_chapters, get_ebook, get_matching_audio_history, save_audio_history,
        )
        from services.media_manager import get_media_manager

        script = get_script(script_id)
        if script is None:
            global_manager.release_model()
            raise HTTPException(status_code=404, detail="剧本不存在")

        book_id = script.get("book_id")
        chapters = get_chapters(book_id) if book_id else []
        chapter = next((c for c in chapters if c["chapter_index"] == chapter_index), None)
        if chapter is None:
            global_manager.release_model()
            raise HTTPException(status_code=404, detail=f"章节 {chapter_index} 不存在")

        chapter_title = chapter.get("title", f"chapter_{chapter_index}")

        # 获取书名用于导出文件名
        book = get_ebook(book_id) if book_id else None
        book_title = book.get("title", "") if book else ""

        lines = get_script_lines(script_id, chapter_index)
        if not lines:
            global_manager.release_model()
            raise HTTPException(status_code=400, detail="本章暂无台词")

        # 检查所有角色是否已配置智能体
        for line in lines:
            role = line.get("role", "")
            config = get_character_config(script_id, role) if role else None
            if not config or not config.get("agent_id"):
                global_manager.release_model()
                raise HTTPException(
                    status_code=400,
                    detail=f"角色「{role}」尚未配置配音智能体，无法导出"
                )

        # 加载 CosyVoice 模型（用于合成缺失的音频）
        from core.model_manager import ensure_cosyvoice_loaded
        if not await asyncio.to_thread(ensure_cosyvoice_loaded):
            global_manager.release_model()
            raise HTTPException(status_code=500, detail="CosyVoice模型加载失败")

        cosyvoice_model = _get_cosyvoice_model()
        media_mgr = get_media_manager()

        # 处理每条语句：根据配置匹配历史音频；无匹配则合成保存
        audio_paths_info = []
        wav_segments = []  # [(wav_bytes, sample_rate, line)]
        generated_count = 0

        for line in lines:
            line_id = line["id"]
            role = line.get("role", "")
            text = line.get("content", "")
            instruction = line.get("instruction", "")
            tone = line.get("tone", "")

            config = get_character_config(script_id, role)
            agent_id = config.get("agent_id", "")
            line_seed = int(line.get("seed", 0))
            seed = line_seed if line_seed != 0 else int(config.get("seed", 0))

            tts_cap_id = config.get("tts_capability_id", "")

            # 使用当前角色配置匹配音频历史（与前端 batch-match 一致）
            matched_history = get_matching_audio_history(line_id, text, role, tone, instruction, agent_id, seed, tts_capability_id=tts_cap_id)
            audio_path = matched_history["audio_path"] if matched_history else ""

            wav_bytes = None
            sample_rate = None

            if audio_path:
                file_info = media_mgr.get_file_by_path(audio_path)
                full_path = file_info["absolute_path"] if file_info else ""
                if full_path and os.path.exists(full_path):
                    with open(full_path, "rb") as f:
                        wav_bytes = f.read()
                    # 读取采样率
                    import wave as wave_module
                    with wave_module.open(full_path, "rb") as wf:
                        sample_rate = wf.getframerate()

            if wav_bytes is None:
                # 合成并保存到历史记录
                agent = _get_agent(agent_id)
                if agent is None:
                    global_manager.release_model()
                    raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

                add_log(f"[导出] 合成 line_id={line_id}, role='{role}'")
                try:
                    from infrastructure.websocket_broadcast import ws_broadcast_manager
                    asyncio.create_task(ws_broadcast_manager.broadcast_line_generating(script_id, line_id))
                except Exception as e:
                    add_log(f"[导出] WebSocket通知失败: {e}", "WARNING")

                wav_bytes, sample_rate = await _synthesize_line_to_wav(line, agent, seed)

                # 保存到 media manager
                filename = f"script_line_{line_id}_{int(time.time())}.wav"
                new_audio_path = media_mgr.save_file(
                    module="tts",
                    filename=filename,
                    content=wav_bytes,
                    category="audio"
                )
                save_audio_history(line_id, text, role, tone, instruction, agent_id, seed, new_audio_path, tts_capability_id=tts_cap_id)
                audio_path = new_audio_path
                generated_count += 1

                try:
                    from infrastructure.websocket_broadcast import ws_broadcast_manager
                    asyncio.create_task(ws_broadcast_manager.broadcast_audio_generated(script_id, line_id))
                except Exception as e:
                    add_log(f"[导出] WebSocket通知失败: {e}", "WARNING")
                add_log(f"[导出] 合成完成并保存到历史记录: {new_audio_path}")

            wav_segments.append((wav_bytes, sample_rate, line))
            audio_paths_info.append({"line_id": line_id, "audio_path": audio_path})

        add_log(f"[导出] 共 {len(wav_segments)} 条，新生成 {generated_count} 条")

        # 合并所有 wav 文件
        try:
            merged_wav_bytes, lines_with_duration = merge_wav_segments(wav_segments)
        except ValueError as e:
            global_manager.release_model()
            raise HTTPException(status_code=500, detail=str(e))

        # 生成 SRT
        srt_content = _build_srt(lines_with_duration)

        # 打包为 ZIP，文件名包含书名和章节名
        import zipfile
        zip_buf = BytesIO()
        illegal_chars = r'\/:*?"<>|'
        safe_chapter = "".join(c for c in chapter_title if c not in illegal_chars) or f"chapter_{chapter_index}"
        safe_book = "".join(c for c in book_title if c not in illegal_chars) if book_title else ""
        # 导出基础名：书名_章节名（书名为空则只用章节名）
        export_base = f"{safe_book}_{safe_chapter}" if safe_book else safe_chapter
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{export_base}.wav", merged_wav_bytes)
            zf.writestr(f"{export_base}.srt", srt_content.encode("utf-8"))

        zip_bytes = zip_buf.getvalue()

        global_manager.release_model()
        add_log(f"[导出] 完成: {export_base}.zip, 大小={len(zip_bytes)} bytes")

        # 通过响应头传递 audio_paths 信息
        # HTTP 头只支持 latin-1，中文文件名需用 RFC 5987 的 filename* 编码
        import urllib.parse
        info_json = json.dumps({"audio_paths": audio_paths_info, "filename": f"{export_base}.zip"})
        encoded_info = urllib.parse.quote(info_json)
        encoded_title = urllib.parse.quote(f"{export_base}.zip")

        from fastapi.responses import Response
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=\"export.zip\"; filename*=UTF-8''{encoded_title}",
                "X-Export-Info": encoded_info,
            }
        )

    except HTTPException:
        global_manager.release_model()
        raise
    except Exception as e:
        global_manager.release_model()
        import traceback
        add_log(f"[导出] 异常: {e}", "ERROR")
        add_log(traceback.format_exc(), "ERROR")
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.post("/api/audio/synthesize-chapter")
async def synthesize_chapter_audio(script_id: int, chapter_index: int):
    """整章配音：合成音频并保存到历史记录，不直接下载。

    复用 export_chapter_audio 的合成逻辑，但将结果保存到 MediaManager 和 chapter_audio_history 表。
    """
    from core.global_manager import global_manager

    if global_manager.is_model_busy():
        raise HTTPException(status_code=400, detail="系统繁忙，请稍后再试")

    if not global_manager.try_acquire_model("cosyvoice"):
        raise HTTPException(status_code=400, detail="系统繁忙，请稍后再试")

    try:
        from repositories import (
            get_script, get_script_lines, get_character_config,
            get_chapters, get_matching_audio_history, save_audio_history,
            save_chapter_audio_history
        )
        from services.media_manager import get_media_manager

        script = get_script(script_id)
        if script is None:
            global_manager.release_model()
            raise HTTPException(status_code=404, detail="剧本不存在")

        book_id = script.get("book_id")
        chapters = get_chapters(book_id) if book_id else []
        chapter = next((c for c in chapters if c["chapter_index"] == chapter_index), None)
        if chapter is None:
            global_manager.release_model()
            raise HTTPException(status_code=404, detail=f"章节 {chapter_index} 不存在")

        chapter_title = chapter.get("title", f"chapter_{chapter_index}")

        lines = get_script_lines(script_id, chapter_index)
        if not lines:
            global_manager.release_model()
            raise HTTPException(status_code=400, detail="本章暂无台词")

        # 检查所有角色是否已配置智能体或云端能力
        for line in lines:
            role = line.get("role", "")
            config = get_character_config(script_id, role) if role else None
            if not config:
                global_manager.release_model()
                raise HTTPException(
                    status_code=400,
                    detail=f"角色「{role}」尚未配置配音，无法配音"
                )
            tts_check = _resolve_tts_params(config, int(line.get("seed", 0)))
            if not tts_check["is_cloud"] and not tts_check["agent_id"]:
                global_manager.release_model()
                raise HTTPException(
                    status_code=400,
                    detail=f"角色「{role}」尚未配置配音智能体或云端能力，无法配音"
                )

        from core.model_executor import ModelExecutor
        executor = ModelExecutor()
        
        media_mgr = get_media_manager()

        # 处理每条语句：根据配置匹配历史音频；无匹配则合成保存
        audio_paths_info = []
        wav_segments = []
        generated_count = 0

        for line in lines:
            line_id = line["id"]
            role = line.get("role", "")
            text = line.get("content", "")
            instruction = line.get("instruction", "")
            tone = line.get("tone", "")

            config = get_character_config(script_id, role)
            tts = _resolve_tts_params(config, int(line.get("seed", 0)))
            agent_id = tts["agent_id"]
            seed = tts["seed"]

            config_tts_cap_id = config.get("tts_capability_id", "") or ""
            tts_cap_id = config_tts_cap_id
            matched_history = get_matching_audio_history(line_id, text, role, tone, instruction, agent_id, seed, tts_capability_id=tts_cap_id)
            audio_path = matched_history["audio_path"] if matched_history else ""

            wav_bytes = None
            sample_rate = None

            if audio_path:
                file_info = media_mgr.get_file_by_path(audio_path)
                full_path = file_info["absolute_path"] if file_info else ""
                if full_path and os.path.exists(full_path):
                    with open(full_path, "rb") as f:
                        wav_bytes = f.read()
                    import wave as wave_module
                    with wave_module.open(full_path, "rb") as wf:
                        sample_rate = wf.getframerate()

            if wav_bytes is None:
                add_log(f"[整章配音] 合成 line_id={line_id}, role='{role}'")
                try:
                    from infrastructure.websocket_broadcast import ws_broadcast_manager
                    asyncio.create_task(ws_broadcast_manager.broadcast_line_generating(script_id, line_id))
                except Exception as e:
                    add_log(f"[整章配音] WebSocket通知失败: {e}", "WARNING")

                wav_bytes, sample_rate = await executor.execute_text_to_speech_wav(
                    text, capability_id=tts["capability_id"],
                    agent_id=tts["agent_id"], tone=tone, instruction=instruction,
                    seed=tts["seed"], extra_params=tts["extra_params"]
                )

                filename = f"script_line_{line_id}_{int(time.time())}.wav"
                new_audio_path = media_mgr.save_file(
                    module="tts", filename=filename, content=wav_bytes, category="audio"
                )
                save_audio_history(line_id, text, role, tone, instruction, agent_id, seed, new_audio_path, tts_capability_id=tts_cap_id)
                audio_path = new_audio_path
                generated_count += 1

                try:
                    from infrastructure.websocket_broadcast import ws_broadcast_manager
                    asyncio.create_task(ws_broadcast_manager.broadcast_audio_generated(script_id, line_id))
                except Exception as e:
                    add_log(f"[整章配音] WebSocket通知失败: {e}", "WARNING")
                add_log(f"[整章配音] 合成完成并保存: {new_audio_path}")

            wav_segments.append((wav_bytes, sample_rate, line))
            audio_paths_info.append({"line_id": line_id, "audio_path": audio_path})

        add_log(f"[整章配音] 共 {len(wav_segments)} 条，新生成 {generated_count} 条")

        # 合并所有 wav 文件
        try:
            merged_wav_bytes, lines_with_duration = merge_wav_segments(wav_segments)
        except ValueError as e:
            global_manager.release_model()
            raise HTTPException(status_code=500, detail=str(e))

        # 生成 SRT
        srt_content = _build_srt(lines_with_duration)

        # 保存音频和SRT到 MediaManager
        timestamp = int(time.time())
        audio_filename = f"chapter_{script_id}_{chapter_index}_{timestamp}.wav"
        srt_filename = f"chapter_{script_id}_{chapter_index}_{timestamp}.srt"
        audio_rel_path = media_mgr.save_file(
            module="tts", filename=audio_filename, content=merged_wav_bytes, category="audio"
        )
        srt_rel_path = media_mgr.save_file(
            module="tts", filename=srt_filename, content=srt_content.encode("utf-8"), category="document"
        )

        total_duration = sum(d for _, d in lines_with_duration)
        file_size = len(merged_wav_bytes)

        # 保存到历史表
        history_id = save_chapter_audio_history(
            script_id, chapter_index, chapter_title,
            audio_rel_path, srt_rel_path, total_duration,
            len(lines_with_duration), generated_count, file_size
        )

        global_manager.release_model()
        add_log(f"[整章配音] 完成: history_id={history_id}, 时长={total_duration:.1f}s")

        return {
            "success": True,
            "history_id": history_id,
            "duration": total_duration,
            "line_count": len(lines_with_duration),
            "generated_count": generated_count,
            "file_size": file_size,
            "audio_paths": audio_paths_info,
        }

    except HTTPException:
        global_manager.release_model()
        raise
    except Exception as e:
        global_manager.release_model()
        import traceback
        add_log(f"[整章配音] 异常: {e}", "ERROR")
        add_log(traceback.format_exc(), "ERROR")
        raise HTTPException(status_code=500, detail=f"配音失败: {str(e)}")


@router.get("/api/audio/chapter-history")
async def get_chapter_history(script_id: int, chapter_index: int):
    """获取指定章节的配音历史列表。"""
    from repositories import get_chapter_audio_history
    history = get_chapter_audio_history(script_id, chapter_index)
    return {"success": True, "history": history}


@router.get("/api/audio/chapter-history/download")
async def download_chapter_history(history_id: int):
    """打包下载章节配音历史记录的音频和文稿（ZIP）。"""
    from repositories import get_chapter_audio_history_by_id
    from services.media_manager import get_media_manager

    record = get_chapter_audio_history_by_id(history_id)
    if not record:
        raise HTTPException(status_code=404, detail="历史记录不存在")

    media_mgr = get_media_manager()
    audio_bytes = media_mgr.get_file_content(record["audio_path"])
    srt_bytes = media_mgr.get_file_content(record["srt_path"])

    if audio_bytes is None or srt_bytes is None:
        raise HTTPException(status_code=404, detail="音频或文稿文件丢失")

    import zipfile
    from io import BytesIO
    import urllib.parse

    illegal_chars = r'\/:*?"<>|'
    chapter_title = record.get("chapter_title", "") or f"chapter_{record['chapter_index'] + 1}"
    safe_title = "".join(c for c in chapter_title if c not in illegal_chars)

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{safe_title}.wav", audio_bytes)
        zf.writestr(f"{safe_title}.srt", srt_bytes)

    zip_bytes = zip_buf.getvalue()
    encoded_title = urllib.parse.quote(f"{safe_title}.zip")

    from fastapi.responses import Response
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"chapter.zip\"; filename*=UTF-8''{encoded_title}",
        }
    )

