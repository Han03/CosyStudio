import os
import json
import asyncio

from fastapi import APIRouter, HTTPException, Request, File, UploadFile, Form

from utils.logger import logger
from core.global_manager import global_manager

router = APIRouter()

from core.paths import AGENTS_DATA_DIR

cosyvoice_model = global_manager.cosyvoice_model
agent_manager = global_manager.agent_manager
agent_task_manager = None

try:
    import importlib.util
    _agent_tasks_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models', 'agent_tasks.py')
    if os.path.exists(_agent_tasks_path):
        _agent_tasks_spec = importlib.util.spec_from_file_location('models.agent_tasks', _agent_tasks_path)
        _agent_tasks_module = importlib.util.module_from_spec(_agent_tasks_spec)
        _agent_tasks_spec.loader.exec_module(_agent_tasks_module)
        agent_task_manager = _agent_tasks_module.agent_task_manager
except Exception as e:
    logger.warning(f"agent_tasks 模块加载失败: {e}")


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


def ensure_agent_manager():
    """确保智能体管理器已加载"""
    global agent_manager
    if agent_manager is None:
        from agents.agent_manager import AgentManager
        agent_manager = AgentManager(AGENTS_DATA_DIR)
        global_manager.agent_manager = agent_manager
        add_log("智能体管理器已加载")
    return agent_manager


def refresh_cosyvoice_model():
    """刷新 cosyvoice_model 引用（模型可能在运行时被加载）"""
    global cosyvoice_model
    cosyvoice_model = global_manager.cosyvoice_model
    return cosyvoice_model


def _parse_params(params_str: str) -> dict:
    """解析前端传来的 params JSON 字符串，返回结构化的 {qwen, cosyvoice, dreamlite}"""
    from core.model_manager import get_loadable_categories
    default = {k: {} for k in get_loadable_categories()}
    if not params_str:
        return default
    try:
        parsed = json.loads(params_str)
        if not isinstance(parsed, dict):
            return default
        for key in default:
            if key not in parsed or not isinstance(parsed[key], dict):
                parsed[key] = {}
        return parsed
    except Exception:
        return default


def _preprocess_voice_file(input_path: str, output_path: str, range_start: float = 0, range_end: float = 0) -> bool:
    """将音频文件预处理为 16kHz、单声道、16bit WAV。

    若提供有效的 range_start/range_end（秒），则在重采样后截取对应片段。
    成功返回 True。
    """
    try:
        import soundfile as sf
        import torch
        import torchaudio.transforms

        data, sr = sf.read(input_path, dtype='float32', always_2d=True)
        waveform = torch.from_numpy(data).T

        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)

        transform = torchaudio.transforms.Resample(orig_freq=sr, new_freq=16000)
        waveform = transform(waveform)

        # 根据选定的声音范围截取（基于 16kHz 重采样后的时间）
        if range_end > 0 and range_end > range_start:
            target_sr = 16000
            start_sample = int(range_start * target_sr)
            end_sample = int(range_end * target_sr)
            total_samples = waveform.shape[1]
            start_sample = max(0, min(start_sample, total_samples))
            end_sample = max(start_sample + 1, min(end_sample, total_samples))
            if end_sample > start_sample and (end_sample - start_sample) < total_samples:
                waveform = waveform[:, start_sample:end_sample]
                add_log(f"音频已截取范围: {range_start:.2f}s - {range_end:.2f}s (样本 {start_sample}-{end_sample})")

        sf.write(output_path, waveform.T.numpy(), 16000, subtype='PCM_16')
        return True
    except Exception as e:
        add_log(f"音频文件预处理失败: {e}", "ERROR")
        return False


def _validate_audio_duration(audio_path: str, min_duration: float = 2.0) -> float:
    """验证音频时长，返回时长（秒）。不满足要求时抛出 HTTPException。"""
    import librosa
    try:
        audio, sr = librosa.load(audio_path, sr=24000)
        duration = len(audio) / sr
        if duration < min_duration:
            raise HTTPException(status_code=400, detail=f"语音文件太短，至少需要{min_duration}秒")
        return duration
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"音频文件读取失败: {str(e)}")


def _parse_voice_tones(voice_tones_str: str) -> list:
    """解析前端传来的 voice_tones JSON 字符串。"""
    if not voice_tones_str:
        return []
    try:
        parsed = json.loads(voice_tones_str)
        if not isinstance(parsed, list):
            return []
        result = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            tone = item.get("tone", "").strip()
            if not tone:
                continue
            result.append({
                "tone": tone,
                "prompt_text": item.get("prompt_text", ""),
                "voice_path": item.get("voice_path", ""),
                "original_path": item.get("original_path", ""),
                "range_start": float(item.get("range_start", 0) or 0),
                "range_end": float(item.get("range_end", 0) or 0),
            })
        return result
    except Exception:
        return []


def _sanitize_filename(name: str) -> str:
    """将语气名称转换为安全的文件名。"""
    import re
    return re.sub(r'[^\w\u4e00-\u9fff]', '_', name).strip('_') or 'tone'


async def _process_tone_voice_files(agent_id: str, voice_tones: list, form) -> list:
    """处理语气音色文件上传，保存原始文件和处理后文件。

    - original_path: 原始上传文件（保留原始格式，用于编辑时波形显示和重新截取）
    - voice_path: 处理后文件（16kHz、单声道、16bit WAV，已按范围截取，用于 speaker 注册）
    """
    agent_tones_dir = os.path.join(AGENTS_DATA_DIR, agent_id, "tones")
    os.makedirs(agent_tones_dir, exist_ok=True)

    for i, vt in enumerate(voice_tones):
        file_key = f"tone_file_{i}"
        uploaded = form.get(file_key)
        if uploaded is None or not hasattr(uploaded, 'read'):
            continue

        safe_name = _sanitize_filename(vt['tone'])
        original_ext = os.path.splitext(getattr(uploaded, 'filename', '') or '')[1] or '.wav'
        original_path = os.path.join(agent_tones_dir, f"{safe_name}_original{original_ext}")
        processed_path = os.path.join(agent_tones_dir, f"{safe_name}.wav")

        content = await uploaded.read()
        with open(original_path, "wb") as f:
            f.write(content)

        range_start = float(vt.get("range_start", 0) or 0)
        range_end = float(vt.get("range_end", 0) or 0)
        if not _preprocess_voice_file(original_path, processed_path, range_start, range_end):
            raise HTTPException(status_code=400, detail=f"语气「{vt['tone']}」的语音文件预处理失败")

        vt["original_path"] = original_path
        vt["voice_path"] = processed_path
        add_log(f"语气「{vt['tone']}」原始文件已保存: {original_path}")
        add_log(f"语气「{vt['tone']}」处理文件已保存: {processed_path}")

    return voice_tones


def _cleanup_removed_tone_files(agent_id: str, old_tones: list, new_tones: list):
    """清理被移除的语气配置对应的文件。"""
    new_tone_names = {vt["tone"] for vt in new_tones}
    for old_vt in old_tones:
        if old_vt["tone"] not in new_tone_names:
            for path_key in ("voice_path", "original_path"):
                old_path = old_vt.get(path_key, "")
                if old_path and os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                        add_log(f"已清理语气「{old_vt['tone']}」的{path_key}: {old_path}")
                    except Exception:
                        pass


def _tone_speaker_id(agent_id: str, tone: str) -> str:
    """生成语气对应的 speaker_id。"""
    return f"{agent_id}__{_sanitize_filename(tone)}"


def _register_tone_speakers(agent_id: str, voice_tones: list):
    """为语气配置注册 CosyVoice speaker。

    每个语气对应一个独立的 speaker_id，注册成功后在 voice_tones 中写入 speaker_id。
    """
    from core.model_manager import ensure_cosyvoice_loaded
    if not ensure_cosyvoice_loaded():
        add_log("CosyVoice 模型未加载，跳过语气 speaker 注册", "WARNING")
        return

    refresh_cosyvoice_model()
    if cosyvoice_model is None:
        return

    for vt in voice_tones:
        voice_path = vt.get("voice_path", "")
        prompt_text = vt.get("prompt_text", "")
        if not voice_path or not os.path.exists(voice_path) or not prompt_text:
            add_log(f"语气「{vt['tone']}」缺少语音文件或提示文本，跳过注册", "WARNING")
            continue

        spk_id = _tone_speaker_id(agent_id, vt["tone"])
        add_log(f"注册语气 speaker: {spk_id}")
        result = cosyvoice_model.add_custom_speaker(spk_id, voice_path, prompt_text)
        if result.get("status") == "success":
            vt["speaker_id"] = spk_id
            add_log(f"语气「{vt['tone']}」speaker 注册成功: {spk_id}")
        else:
            add_log(f"语气「{vt['tone']}」speaker 注册失败: {result.get('error', '未知错误')}", "ERROR")


def _unregister_tone_speakers(agent_id: str, voice_tones: list):
    """注销语气配置对应的 CosyVoice speaker。"""
    refresh_cosyvoice_model()
    if cosyvoice_model is None:
        return

    for vt in voice_tones:
        spk_id = vt.get("speaker_id", "") or _tone_speaker_id(agent_id, vt["tone"])
        try:
            cosyvoice_model.remove_speaker(spk_id)
            add_log(f"已注销语气 speaker: {spk_id}")
        except Exception as e:
            add_log(f"注销语气 speaker 失败 {spk_id}: {e}", "WARNING")


def _path_to_url(path: str) -> str:
    """将 agents_data 目录下的文件系统路径转为前端可访问的 URL。

    兼容旧数据：存储的路径可能基于旧的 AGENTS_DATA_DIR（如 backend/agents/data/），
    只要路径包含 <agent_id>/tones/<filename> 结构即可正确生成 URL。
    """
    if not path:
        return ""
    try:
        normalized = path.replace("\\", "/")
        parts = normalized.split("/")
        # 从末尾提取 tones/<filename>，再往前取 agent_id
        if len(parts) >= 3 and parts[-2] == "tones":
            agent_id = parts[-3]
            filename = parts[-1]
            return f"/agents_data/{agent_id}/tones/{filename}"
        # fallback: 尝试基于当前 AGENTS_DATA_DIR 计算相对路径
        rel = os.path.relpath(path, AGENTS_DATA_DIR)
        rel = rel.replace("\\", "/")
        return f"/agents_data/{rel}"
    except Exception:
        return ""


def _url_to_path(url: str) -> str:
    """将前端 URL 转回文件系统路径。"""
    if not url:
        return ""
    if url.startswith("/agents_data/"):
        rel = url[len("/agents_data/"):]
        return os.path.normpath(os.path.join(AGENTS_DATA_DIR, rel.replace("/", os.sep)))
    return url


def _agent_voice_tones_to_urls(agent: dict) -> dict:
    """将 agent 的 voice_tones 中的路径字段转为 URL，返回处理后的 agent 副本。"""
    import copy
    agent = copy.deepcopy(agent)
    for vt in agent.get("voice_tones", []):
        for key in ("voice_path", "original_path"):
            if vt.get(key):
                vt[key] = _path_to_url(vt[key])
    return agent


@router.get("/api/agents")
async def get_agents(page: int = 1, page_size: int = 9, tag: str = "", search: str = "",
                     gender: str = "", age: str = "", agent_id: str = None):
    """获取智能体列表（支持分页、标签筛选、搜索、性别筛选、年龄筛选）
    或获取单个智能体详情（传入 agent_id 时）"""
    mgr = ensure_agent_manager()
    if agent_id:
        agent = mgr.get_agent(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")
        return _agent_voice_tones_to_urls(agent)
    result = mgr.get_agents_paginated(page=page, page_size=page_size, tag=tag, search=search,
                                       gender=gender, age=age)
    result["items"] = [_agent_voice_tones_to_urls(a) for a in result["items"]]
    return result


@router.get("/api/agents/tags")
async def get_agent_tags():
    """获取所有标签列表"""
    mgr = ensure_agent_manager()
    tags = mgr.get_all_tags()
    return {"tags": tags}


@router.get("/api/agents/voice-preview")
async def get_agent_voice_preview(agent_id: str, tone_index: int = 0):
    """获取智能体的音色试听音频。

    直接返回该智能体指定语气的音色参考音频文件（WAV）。
    - tone_index: 语气索引，默认 0（第一个语气）
    """
    from fastapi.responses import FileResponse

    mgr = ensure_agent_manager()
    agent = mgr.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

    voice_tones = agent.get("voice_tones", [])
    if not voice_tones:
        raise HTTPException(status_code=400, detail="该智能体暂无语气音色配置")

    if tone_index < 0 or tone_index >= len(voice_tones):
        tone_index = 0

    tone_info = voice_tones[tone_index]
    voice_path = tone_info.get("voice_path", "")

    if not voice_path:
        raise HTTPException(status_code=400, detail="该语气暂无音色参考音频")

    if not os.path.exists(voice_path) or not os.path.isfile(voice_path):
        raise HTTPException(status_code=404, detail="音色参考音频文件不存在")

    tone_name = tone_info.get("tone", f"tone_{tone_index}")
    safe_name = "".join(c for c in tone_name if c.isalnum() or c in ('-', '_')) or "preview"

    add_log(f"[音色试听] agent={agent_id}, tone={tone_name}, file={voice_path}")

    return FileResponse(
        path=voice_path,
        media_type="audio/wav",
        filename=f"{safe_name}.wav",
    )





@router.post("/api/agents")
async def create_agent(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    gender: str = Form(""),
    age: str = Form(""),
    tags: str = Form("[]"),
    voice_tones: str = Form("[]")
):
    """
    创建智能体。
    - voice_tones: 语气音色配置 JSON，每项 {tone, prompt_text, voice_path?, range_start?, range_end?}
    - tags: 标签 JSON 数组字符串
    """
    mgr = ensure_agent_manager()
    parsed_voice_tones = _parse_voice_tones(voice_tones)

    try:
        parsed_tags = json.loads(tags) if tags else []
        if not isinstance(parsed_tags, list):
            parsed_tags = []
        parsed_tags = [str(t).strip() for t in parsed_tags if str(t).strip()]
    except Exception:
        parsed_tags = []

    add_log(f"正在创建智能体: {name}, 性别: {gender}, 年龄: {age}, 标签: {parsed_tags}, 语气配置数: {len(parsed_voice_tones)}")
    agent = mgr.create_agent(name, description, voice_tones=[], gender=gender, age=age, tags=parsed_tags)
    agent_id = agent["id"]
    add_log(f"智能体记录已创建，ID: {agent_id}")

    if parsed_voice_tones:
        form = await request.form()
        try:
            parsed_voice_tones = await _process_tone_voice_files(agent_id, parsed_voice_tones, form)
            _register_tone_speakers(agent_id, parsed_voice_tones)
            mgr.update_agent(agent_id, voice_tones=parsed_voice_tones, trained=True)
            add_log(f"语气音色配置已保存: {len(parsed_voice_tones)} 项")
        except HTTPException:
            _unregister_tone_speakers(agent_id, parsed_voice_tones)
            mgr.delete_agent(agent_id)
            raise
        except Exception as e:
            add_log(f"语气音色配置保存失败: {e}", "ERROR")
            _unregister_tone_speakers(agent_id, parsed_voice_tones)
            mgr.delete_agent(agent_id)
            raise HTTPException(status_code=400, detail=f"语气音色配置保存失败: {str(e)}")
    else:
        mgr.update_agent(agent_id, trained=True)

    add_log(f"智能体 '{name}' 创建完成")
    return {
        "success": True,
        "agent_id": agent_id,
        "name": name,
        "description": description,
        "status": "ready",
        "message": "智能体创建成功"
    }


@router.put("/api/agents")
async def update_agent(
    agent_id: str,
    request: Request,
    name: str = Form(None),
    description: str = Form(None),
    gender: str = Form(None),
    age: str = Form(None),
    tags: str = Form(None),
    voice_tones: str = Form(None),
):
    """编辑智能体（基础字段 + 标签 + 语气音色配置）。

    - voice_tones: 语气音色配置 JSON，每项 {tone, prompt_text, voice_path?, range_start?, range_end?}
    - tags: 标签 JSON 数组字符串
    """
    mgr = ensure_agent_manager()
    agent = mgr.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

    updates = {}
    if name is not None:
        updates["name"] = name
    if description is not None:
        updates["description"] = description
    if gender is not None:
        updates["gender"] = gender
    if age is not None:
        updates["age"] = age
    if tags is not None:
        try:
            parsed_tags = json.loads(tags) if tags else []
            if not isinstance(parsed_tags, list):
                parsed_tags = []
            parsed_tags = [str(t).strip() for t in parsed_tags if str(t).strip()]
            updates["tags"] = parsed_tags
        except Exception:
            pass

    if voice_tones is not None:
        parsed_voice_tones = _parse_voice_tones(voice_tones)
        old_voice_tones = agent.get("voice_tones", [])

        # 前端传回的 voice_path/original_path 可能是 URL，转回文件系统路径
        for vt in parsed_voice_tones:
            if vt.get("voice_path"):
                vt["voice_path"] = _url_to_path(vt["voice_path"])
            if vt.get("original_path"):
                vt["original_path"] = _url_to_path(vt["original_path"])

        if parsed_voice_tones:
            form = await request.form()
            parsed_voice_tones = await _process_tone_voice_files(agent_id, parsed_voice_tones, form)

        # 计算被移除的语气，注销 speaker
        old_tone_map = {vt["tone"]: vt for vt in old_voice_tones}
        new_tone_names = {vt["tone"] for vt in parsed_voice_tones}
        removed_tones = [vt for vt in old_voice_tones if vt["tone"] not in new_tone_names]
        if removed_tones:
            _unregister_tone_speakers(agent_id, removed_tones)

        # 处理每个语气：检测范围变化，必要时从原始文件重新截取
        for vt in parsed_voice_tones:
            old_vt = old_tone_map.get(vt["tone"])
            voice_path = vt.get("voice_path", "")
            original_path = vt.get("original_path", "")
            prompt_text = vt.get("prompt_text", "")
            range_start = vt.get("range_start", 0)
            range_end = vt.get("range_end", 0)

            # 判断是否需要重新截取（范围变了，且有原始文件）
            needs_reprocess = False
            if old_vt:
                old_range_start = old_vt.get("range_start", 0)
                old_range_end = old_vt.get("range_end", 0)
                if abs(range_start - old_range_start) > 0.01 or abs(range_end - old_range_end) > 0.01:
                    needs_reprocess = True
                # 提示文本变了也需要重新注册 speaker
                if prompt_text != old_vt.get("prompt_text", ""):
                    needs_reprocess = True

            if needs_reprocess and original_path and os.path.exists(original_path) and prompt_text:
                # 从原始文件重新截取
                if not _preprocess_voice_file(original_path, voice_path, range_start, range_end):
                    raise HTTPException(status_code=400, detail=f"语气「{vt['tone']}」的语音文件重新截取失败")
                add_log(f"语气「{vt['tone']}」已根据新范围重新截取")
                _register_tone_speakers(agent_id, [vt])
            elif old_vt and not needs_reprocess:
                # 保留旧的 speaker_id
                vt["speaker_id"] = old_vt.get("speaker_id", "")
            elif not old_vt and voice_path and os.path.exists(voice_path) and prompt_text:
                # 新增的语气（已有处理后的文件）
                _register_tone_speakers(agent_id, [vt])

        _cleanup_removed_tone_files(agent_id, old_voice_tones, parsed_voice_tones)
        updates["voice_tones"] = parsed_voice_tones
        add_log(f"智能体 {agent_id} 语气音色配置已更新: {len(parsed_voice_tones)} 项")

    if updates:
        updated = mgr.update_agent(agent_id, **updates)
        if "error" in updated:
            raise HTTPException(status_code=400, detail=updated["error"])
    else:
        updated = agent

    add_log(f"智能体 {agent_id} 已更新")
    return {"success": True, "agent": _agent_voice_tones_to_urls(updated)}


@router.delete("/api/agents")
async def delete_agent(agent_id: str):
    """删除智能体"""
    mgr = ensure_agent_manager()
    agent = mgr.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="智能体不存在")

    add_log(f"正在删除智能体: {agent_id}")

    # 注销所有语气 speaker
    voice_tones = agent.get("voice_tones", [])
    if voice_tones:
        _unregister_tone_speakers(agent_id, voice_tones)

    # 同时尝试移除旧的默认 speaker（兼容历史数据）
    refresh_cosyvoice_model()
    if cosyvoice_model is not None:
        try:
            cosyvoice_model.remove_speaker(agent_id)
        except Exception as e:
            add_log(f"移除默认说话人失败: {e}", "WARNING")

    result = mgr.delete_agent(agent_id)
    return {"success": True, "message": result.get("message", "智能体已删除")}


@router.get("/api/agents/tasks")
async def get_task_status(task_id: str):
    """查询任务状态"""
    if agent_task_manager is None:
        raise HTTPException(status_code=404, detail="任务管理器未加载")
    task = agent_task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/api/agents/tasks")
async def get_all_tasks():
    """获取所有任务"""
    if agent_task_manager is None:
        return []
    return agent_task_manager.get_all_tasks()


@router.get("/api/voices")
async def get_voices():
    """获取可用音色列表"""
    refresh_cosyvoice_model()
    voices = []
    if cosyvoice_model is not None and cosyvoice_model.is_loaded():
        voices = cosyvoice_model.list_speakers()
    voice_list = [{"id": v, "name": v} for v in voices]
    return {"voices": voice_list}


@router.get("/api/voices/available")
async def get_available_voices_api():
    """获取可用音色列表（简化版）"""
    refresh_cosyvoice_model()
    if cosyvoice_model is None or not cosyvoice_model.is_loaded():
        return {"voices": []}
    return {"voices": cosyvoice_model.list_speakers()}


@router.get("/api/voices/list")
async def list_registered_voices():
    """列出已注册音色"""
    refresh_cosyvoice_model()
    if cosyvoice_model is None or not cosyvoice_model.is_loaded():
        return {"voices": []}
    return {"voices": cosyvoice_model.list_speakers()}


@router.post("/api/voices/register")
async def register_voice(request: Request):
    """注册音色"""
    refresh_cosyvoice_model()
    if cosyvoice_model is None:
        raise HTTPException(status_code=500, detail="CosyVoice模型未加载")

    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"请求体解析失败: {str(e)}")

    agent_id = data.get("agent_id")
    voice_path = data.get("voice_path")
    prompt_text = data.get("prompt_text", "")

    if not agent_id or not voice_path:
        raise HTTPException(status_code=400, detail="缺少agent_id或voice_path")

    if not os.path.exists(voice_path):
        raise HTTPException(status_code=400, detail=f"语音文件不存在: {voice_path}")

    try:
        cosyvoice_model.register_speaker(agent_id, voice_path, prompt_text)
        add_log(f"注册说话人成功: {agent_id}")
        return {"success": True, "message": f"说话人 {agent_id} 注册成功"}
    except Exception as e:
        add_log(f"注册说话人失败: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=f"注册说话人失败: {str(e)}")


@router.post("/api/voices/unregister")
async def unregister_voice(request: Request):
    """注销音色"""
    refresh_cosyvoice_model()
    if cosyvoice_model is None:
        raise HTTPException(status_code=500, detail="CosyVoice模型未加载")

    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"请求体解析失败: {str(e)}")

    agent_id = data.get("agent_id")
    if not agent_id:
        raise HTTPException(status_code=400, detail="缺少agent_id")

    try:
        cosyvoice_model.unregister_speaker(agent_id)
        add_log(f"注销说话人成功: {agent_id}")
        return {"success": True, "message": f"说话人 {agent_id} 注销成功"}
    except Exception as e:
        add_log(f"注销说话人失败: {e}", "ERROR")
        raise HTTPException(status_code=500, detail=f"注销说话人失败: {str(e)}")


# ============================================================
# 会话历史
# ============================================================

@router.get("/api/agents/history")
async def get_agent_history(agent_id: str):
    """获取指定智能体的会话历史。

    返回结构: {"agent_id": "...", "messages": [...], "count": N}
    messages 元素: {"role": "user"|"assistant", "content": "..."}
    """
    from domain.conversation import get_conversation_manager
    conv_mgr = get_conversation_manager()
    session = conv_mgr.get_or_create_session(agent_id)
    history = session.get_history()
    add_log(f"[History] 加载历史（agent={agent_id}），共 {len(history)} 条消息")
    return {"agent_id": agent_id, "messages": history, "count": len(history)}


@router.delete("/api/agents/history")
async def clear_agent_history(agent_id: str):
    """清空指定智能体的通话会话历史（内存 + 文件）。

    返回结构: {"success": True, "message": "..."}
    """
    from domain.conversation import get_conversation_manager
    conv_mgr = get_conversation_manager()
    conv_mgr.clear_session(agent_id)
    add_log(f"[History] 已清空历史（agent={agent_id}）")
    return {"success": True, "message": "历史已清空", "agent_id": agent_id}


# ============================================================
# 记忆管理 API（向量库记忆）
# ============================================================

@router.get("/api/agents/memories")
async def get_agent_memories(agent_id: str):
    """获取指定智能体的所有记忆摘要（向量库）。

    返回结构: {"agent_id": "...", "memories": [...], "count": N}
    memories 元素: {"id": N, "summary": "...", "metadata": {...}, "created_at": ...}
    """
    from services.vector_store import get_all_memories, count_memories
    memories = get_all_memories(agent_id)
    count = count_memories(agent_id)
    add_log(f"[Memories] 加载记忆（agent={agent_id}），共 {count} 条")
    return {"agent_id": agent_id, "memories": memories, "count": count}


@router.delete("/api/agents/memories")
async def delete_agent_memory(agent_id: str, memory_id: int):
    """删除指定智能体的单条记忆。

    返回结构: {"success": True/False, "message": "..."}
    """
    from services.vector_store import delete_memory
    success = delete_memory(agent_id, memory_id)
    if success:
        add_log(f"[Memories] 已删除记忆（agent={agent_id}, id={memory_id}）")
        return {"success": True, "message": "记忆已删除"}
    else:
        return {"success": False, "message": "删除失败"}


@router.delete("/api/agents/memories/clear")
async def clear_agent_memories(agent_id: str):
    """清空指定智能体的所有记忆（向量库）。

    返回结构: {"success": True, "message": "..."}
    """
    from services.vector_store import clear_memories
    success = clear_memories(agent_id)
    if success:
        add_log(f"[Memories] 已清空所有记忆（agent={agent_id}）")
        return {"success": True, "message": "所有记忆已清空"}
    else:
        return {"success": False, "message": "清空失败"}
