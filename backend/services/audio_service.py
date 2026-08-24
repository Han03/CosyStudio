"""音频服务层 —— 从 api/audio_synthesize.py 提取的 TTS 合成、音频处理与格式化工具。"""

import os
import json
import time
import asyncio
import base64
import wave
from io import BytesIO
from typing import Optional, List, Tuple, Dict, Any, AsyncGenerator

import numpy as np

from utils.logger import logger


# ==============================================================================
# 日志工具
# ==============================================================================

def add_log(message: str, level: str = "INFO"):
    """统一日志输出。"""
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


# ==============================================================================
# TTS 合成辅助
# ==============================================================================

async def synthesize_line_to_wav(line: dict, agent: dict, seed: int = 0) -> tuple:
    """合成单条语句为 WAV bytes，返回 (wav_bytes, sample_rate)。失败抛异常。"""
    from core.model_executor import ModelExecutor

    text = line.get("content", "")
    tone = line.get("tone", "")
    instruction = line.get("instruction", "")
    agent_id = agent.get("id", "")

    executor = ModelExecutor()
    wav_data, sample_rate = await executor.execute_text_to_speech_wav(
        text, capability_id=None, agent_id=agent_id,
        tone=tone, instruction=instruction, seed=seed
    )
    return wav_data, sample_rate


# ==============================================================================
# WAV 文件流式播放（从 play_with_settings / play_script_line 提取的共用逻辑）
# ==============================================================================

async def stream_wav_file_as_pcm(
    full_path: str,
    *,
    volume: float = 1.0,
    pitch: int = 0,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    range_start: float = 0.0,
    range_end: float = 0.0,
    audio_adjust_enabled: bool = False,
) -> AsyncGenerator[dict, None]:
    """读取 WAV 文件并以 PCM chunk 流式输出。

    支持可选的音量/变调/淡入淡出/区间裁剪处理。
    产出 dict 消息: start / pcm_chunk / finish / error
    """
    try:
        with wave.open(full_path, 'rb') as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            raw_data = wf.readframes(n_frames)

        if sample_width == 2:
            y = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
        elif sample_width == 4:
            y = np.frombuffer(raw_data, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            y = np.frombuffer(raw_data, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0

        if n_channels > 1:
            y = y.reshape(-1, n_channels).mean(axis=1)

        # 可选音频处理
        if audio_adjust_enabled:
            if pitch != 0:
                import librosa
                y = librosa.effects.pitch_shift(y, sr=sr, n_steps=pitch)

            y = y * volume

            if range_end > range_start and range_end > 0:
                start_sample = max(0, int(range_start * sr))
                end_sample = min(len(y), int(range_end * sr))
                if end_sample > start_sample:
                    y = y[start_sample:end_sample]

            if fade_in > 0:
                fade_in_samples = min(int(fade_in * sr), len(y))
                if fade_in_samples > 0:
                    y[:fade_in_samples] *= np.linspace(0, 1, fade_in_samples)

            if fade_out > 0:
                fade_out_samples = min(int(fade_out * sr), len(y))
                if fade_out_samples > 0:
                    y[-fade_out_samples:] *= np.linspace(1, 0, fade_out_samples)

        y = np.clip(y, -1.0, 1.0)
        duration = len(y) / sr

        yield {"type": "start", "sample_rate": sr, "duration": duration}

        chunk_size = 8192
        samples_per_chunk = int(chunk_size / 2)
        chunk_index = 0
        for i in range(0, len(y), samples_per_chunk):
            chunk = y[i:i + samples_per_chunk]
            pcm_data = (chunk * 32767).astype(np.int16)
            pcm_bytes = pcm_data.tobytes()
            pcm_b64 = base64.b64encode(pcm_bytes).decode("ascii")
            yield {
                "type": "pcm_chunk",
                "sample_rate": sr,
                "chunk_index": chunk_index,
                "data": pcm_b64,
            }
            chunk_index += 1

        yield {"type": "finish", "sample_rate": sr, "chunk_count": chunk_index}

    except Exception as e:
        add_log(f"[音频服务] WAV 流式播放异常: {e}", "ERROR")
        import traceback
        add_log(traceback.format_exc(), "ERROR")
        yield {"type": "error", "message": str(e)}


# ==============================================================================
# SRT 文稿生成
# ==============================================================================

def format_srt_timestamp(seconds: float) -> str:
    """将秒数格式化为 SRT 时间戳 HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(lines_with_duration: list) -> str:
    """根据 [(line_dict, duration_seconds), ...] 列表生成 SRT 字符串。"""
    srt_parts = []
    current_time = 0.0
    for idx, (line, duration) in enumerate(lines_with_duration, start=1):
        start = current_time
        end = current_time + duration
        role = line.get("role", "")
        content = line.get("content", "")
        text = f"{role}：{content}" if role else content
        srt_parts.append(
            f"{idx}\n"
            f"{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}\n"
            f"{text}\n"
        )
        current_time = end
    return "\n".join(srt_parts)


# ==============================================================================
# WAV 合并工具（从 export_chapter_audio / synthesize_chapter_audio 提取）
# ==============================================================================

def merge_wav_segments(
    wav_segments: List[Tuple[bytes, int, Any]],
    target_sr: Optional[int] = None,
) -> Tuple[bytes, List[Tuple[Any, float]]]:
    """合并多个 WAV 片段为单个 WAV 文件。

    Args:
        wav_segments: [(wav_bytes, sample_rate, line_dict), ...]
        target_sr: 目标采样率，默认取第一个片段的采样率

    Returns:
        (merged_wav_bytes, lines_with_duration)
    """
    if not wav_segments:
        return b"", []

    if target_sr is None:
        target_sr = wav_segments[0][1]

    merged_pcm = bytearray()
    lines_with_duration = []

    for wav_bytes, sr, line in wav_segments:
        with wave.open(BytesIO(wav_bytes), "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        if sample_width != 2:
            raise ValueError("仅支持 16-bit WAV")

        if n_channels > 1:
            arr = np.frombuffer(raw, dtype=np.int16).reshape(-1, n_channels)
            raw = arr.mean(axis=1).astype(np.int16).tobytes()

        if sr != target_sr:
            add_log(f"[音频服务] 警告: 采样率不一致 sr={sr}, target={target_sr}", "WARNING")

        merged_pcm.extend(raw)
        duration = len(raw) / (target_sr * 2)
        lines_with_duration.append((line, duration))

    merged_wav_buf = BytesIO()
    with wave.open(merged_wav_buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(target_sr)
        wf.writeframes(bytes(merged_pcm))

    return merged_wav_buf.getvalue(), lines_with_duration


# ==============================================================================
# TTS 合成并保存为 WAV（从 generate_and_save_audio / play_with_settings 提取）
# ==============================================================================

async def synthesize_and_save(
    text: str,
    agent_id: str,
    tone: str,
    instruction: str,
    seed: int,
    line_id: int,
) -> Tuple[bytes, int, str]:
    """调用 TTS 合成语音，保存为 WAV 文件到 MediaManager。

    Returns:
        (wav_data, sample_rate, audio_path)
    """
    from core.model_executor import ModelExecutor
    from services.media_manager import get_media_manager
    from repositories import save_audio_history

    executor = ModelExecutor()
    sample_rate = None
    audio_data_list = []

    async for audio_chunk in executor.execute_text_to_speech(
        text, stream=True, agent_id=agent_id, tone=tone,
        instruction=instruction, seed=seed,
    ):
        if audio_chunk.get("type") == "pcm_chunk":
            sample_rate = audio_chunk["sample_rate"]
            pcm_b64 = audio_chunk["data"]
            pcm_bytes = base64.b64decode(pcm_b64)
            audio_data_list.append(pcm_bytes)
        elif audio_chunk.get("type") == "error":
            raise RuntimeError(audio_chunk.get("message", "合成失败"))

    if not audio_data_list or not sample_rate:
        raise RuntimeError("合成未返回音频数据")

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
        module="tts", filename=filename, content=wav_data, category="audio"
    )

    return wav_data, sample_rate, audio_path
