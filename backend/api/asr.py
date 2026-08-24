import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse

from core.paths import BIN_DIR

router = APIRouter(prefix="/api/asr", tags=["ASR"])

_whisper_model = None
_whisper_model_name = "base"

_zhconv_available = False
try:
    import zhconv
    _zhconv_available = True
except ImportError:
    pass


def _convert_to_simplified(text: str) -> str:
    """将繁体中文转换为简体中文。优先使用 zhconv，失败则原样返回。"""
    if not text:
        return text
    if _zhconv_available:
        try:
            return zhconv.convert(text, 'zh-cn')
        except Exception:
            pass
    return text


def get_whisper_model(model_name: str = "base"):
    global _whisper_model, _whisper_model_name
    if _whisper_model is None or _whisper_model_name != model_name:
        import whisper
        _whisper_model = whisper.load_model(model_name)
        _whisper_model_name = model_name
    return _whisper_model


ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".webm", ".mp4"}
MAX_FILE_SIZE = 25 * 1024 * 1024


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: Optional[str] = Form(None),
    whisper_model: str = Form("base"),
    force_simplified: bool = Form(True),
    range_start: float = Form(0),
    range_end: float = Form(0),
):
    if not audio.filename:
        raise HTTPException(status_code=400, detail="未上传音频文件")

    ext = Path(audio.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的音频格式: {ext}，支持: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    audio_bytes = await audio.read()
    if not audio_bytes or len(audio_bytes) < 1024:
        raise HTTPException(status_code=400, detail="音频文件为空或过小")
    if len(audio_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="音频文件过大（最大25MB）")

    tmp_path = None
    segment_path = None
    try:
        tmp_dir = tempfile.gettempdir()
        tmp_filename = f"asr_{uuid.uuid4().hex}{ext}"
        tmp_path = os.path.join(tmp_dir, tmp_filename)
        with open(tmp_path, "wb") as f:
            f.write(audio_bytes)

        # 如果指定了有效范围，用 ffmpeg 截取对应片段
        transcribe_path = tmp_path
        if range_end > 0 and range_end > range_start:
            segment_filename = f"asr_seg_{uuid.uuid4().hex}.wav"
            segment_path = os.path.join(tmp_dir, segment_filename)
            duration = range_end - range_start
            ffmpeg_exe = os.path.join(BIN_DIR, "ffmpeg", "ffmpeg.exe")
            cmd = [
                ffmpeg_exe, "-y", "-ss", str(range_start), "-t", str(duration),
                "-i", tmp_path, "-vn", "-ac", "1", "-ar", "16000",
                "-f", "wav", segment_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, timeout=60, text=True,
            )
            if result.returncode != 0 or not os.path.exists(segment_path):
                raise HTTPException(
                    status_code=500,
                    detail=f"音频范围截取失败: {result.stderr[:200] if result.stderr else '未知错误'}",
                )
            transcribe_path = segment_path

        model = get_whisper_model(whisper_model)

        options = {}
        if language:
            options["language"] = language
        elif force_simplified:
            options["language"] = "zh"

        # 用 initial_prompt 引导 Whisper 输出简体中文
        if force_simplified and options.get("language", "zh") == "zh":
            options["initial_prompt"] = (
                "以下是普通话的简体中文转录。"
                "使用简体汉字，例如：什么、这里、那里、这样、那样、为什么、因为、所以、"
                "我们、你们、他们、她们、它们、这个、那个、现在、以后、以前、"
                "可以、可能、应该、需要、知道、觉得、认为、发现、看到、听到。"
            )

        result = model.transcribe(transcribe_path, **options)
        text = result.get("text", "").strip()

        if force_simplified:
            text = _convert_to_simplified(text)

        return JSONResponse(
            content={
                "success": True,
                "text": text,
                "language": result.get("language", language or ""),
                "duration": result.get("duration", 0),
                "segments_count": len(result.get("segments", [])),
            }
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="Whisper 库未安装，请先安装 openai-whisper")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"语音识别失败: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        if segment_path and os.path.exists(segment_path):
            try:
                os.remove(segment_path)
            except Exception:
                pass
