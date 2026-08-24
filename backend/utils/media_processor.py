"""媒体文件处理工具模块。

提供图片、音频的大小限制和压缩功能，确保上传文件符合要求后再传给大模型。
"""

import io
import os
from typing import Optional, Tuple

MAX_FILE_SIZE = 800 * 1024
MAX_IMAGE_SIZE = 800 * 1024
MAX_AUDIO_SIZE = 500 * 1024
MAX_DOCUMENT_SIZE = 100 * 1024

TARGET_IMAGE_SIZE = 200 * 1024
TARGET_AUDIO_SIZE = 512 * 1024


def check_file_size(data: bytes, max_size: int, file_type: str) -> Tuple[bool, str]:
    """检查文件大小是否超过限制。

    参数:
        data: 文件数据
        max_size: 最大允许大小（字节）
        file_type: 文件类型描述

    返回:
        (是否通过检查, 错误信息)
    """
    size = len(data)
    if size > max_size:
        return False, f"{file_type}大小{size/1024:.2f}KB超过{max_size/1024:.0f}KB限制"
    return True, ""


def compress_image(image, target_size: int = TARGET_IMAGE_SIZE) -> Optional[bytes]:
    """压缩图片到指定大小。

    参数:
        image: PIL Image对象
        target_size: 目标大小（字节）

    返回:
        压缩后的图片字节数据，失败返回None
    """
    try:
        original_size = len(image.tobytes())
        
        if original_size <= target_size:
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=90)
            return buffer.getvalue()

        MAX_DIMENSION = 512
        MIN_DIMENSION = 256
        width, height = image.size
        
        ratio = 1.0
        if width > MAX_DIMENSION or height > MAX_DIMENSION:
            ratio = min(MAX_DIMENSION / width, MAX_DIMENSION / height)
        elif width < MIN_DIMENSION or height < MIN_DIMENSION:
            ratio = max(MIN_DIMENSION / width, MIN_DIMENSION / height)
        
        if ratio != 1.0:
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            image = image.resize((new_width, new_height), Image.LANCZOS)

        quality = 90
        step = 5
        
        while quality >= 10:
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality)
            compressed_data = buffer.getvalue()
            
            if len(compressed_data) <= target_size:
                return compressed_data
            
            quality -= step

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=10)
        return buffer.getvalue()

    except Exception as e:
        from utils.logger import add_log
        add_log(f"[MediaProcessor] 图片压缩失败: {e}", "WARNING")
        return None


def compress_audio(audio_np, sample_rate: int = 24000, 
                   target_size: int = TARGET_AUDIO_SIZE) -> Optional[bytes]:
    """压缩音频到指定大小。

    参数:
        audio_np: numpy数组形式的音频数据
        sample_rate: 采样率
        target_size: 目标大小（字节）

    返回:
        压缩后的音频字节数据（WAV格式），失败返回None
    """
    try:
        import soundfile as sf
        
        buffer = io.BytesIO()
        sf.write(buffer, audio_np, sample_rate, format="WAV")
        original_size = buffer.tell()
        
        if original_size <= target_size:
            buffer.seek(0)
            return buffer.read()

        target_duration = (target_size * 8) / (sample_rate * 16)
        original_duration = len(audio_np) / sample_rate
        
        if original_duration > target_duration:
            ratio = target_duration / original_duration
            audio_np = audio_np[::int(1/ratio)]

        buffer = io.BytesIO()
        sf.write(buffer, audio_np, sample_rate, format="WAV")
        return buffer.getvalue()

    except Exception as e:
        from utils.logger import add_log
        add_log(f"[MediaProcessor] 音频压缩失败: {e}", "WARNING")
        return None


def process_image(image_b64: str) -> Tuple[Optional[object], Optional[str], str]:
    """处理图片数据：检查大小、解码、压缩。

    参数:
        image_b64: base64编码的图片数据（可能包含data URI）

    返回:
        (PIL Image对象或None, 保存路径或None, 错误信息)
    """
    try:
        import base64 as _b64
        from PIL import Image

        if isinstance(image_b64, str) and "," in image_b64 and image_b64.startswith("data:"):
            image_b64 = image_b64.split(",", 1)[1]

        image_bytes = _b64.b64decode(image_b64)
        
        ok, msg = check_file_size(image_bytes, MAX_IMAGE_SIZE, "图片")
        if not ok:
            return None, None, msg

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        
        compressed_bytes = compress_image(image)
        if compressed_bytes is None:
            return None, None, "图片压缩失败"

        compressed_image = Image.open(io.BytesIO(compressed_bytes))
        
        from utils.logger import add_log
        add_log(f"[MediaProcessor] 图片处理完成，原始尺寸: {image.size}, 压缩后尺寸: {compressed_image.size}, 大小: {len(compressed_bytes)/1024:.1f}KB")
        
        return compressed_image, None, ""

    except Exception as e:
        return None, None, f"图片处理失败: {str(e)}"


def process_audio(audio_b64: str) -> Tuple[Optional[object], Optional[str], str]:
    """处理音频数据：检查大小、解码、压缩。

    参数:
        audio_b64: base64编码的音频数据（可能包含data URI）

    返回:
        (numpy数组或None, 保存路径或None, 错误信息)
    """
    try:
        import base64 as _b64
        import librosa
        import numpy as np
        import tempfile

        if isinstance(audio_b64, str) and "," in audio_b64 and audio_b64.startswith("data:"):
            audio_b64 = audio_b64.split(",", 1)[1]

        audio_bytes = _b64.b64decode(audio_b64)
        
        ok, msg = check_file_size(audio_bytes, MAX_AUDIO_SIZE, "音频")
        if not ok:
            return None, None, msg

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.write(audio_bytes)
        tmp.close()
        
        try:
            audio_np, sr = librosa.load(tmp.name, sr=24000)
            
            compressed_bytes = compress_audio(audio_np, sr)
            if compressed_bytes is None:
                return None, None, "音频压缩失败"

            import soundfile as sf
            tmp_compressed = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_compressed.write(compressed_bytes)
            tmp_compressed.close()
            
            try:
                compressed_np, _ = librosa.load(tmp_compressed.name, sr=24000)
            finally:
                try:
                    os.remove(tmp_compressed.name)
                except Exception:
                    pass

            from utils.logger import add_log
            add_log(f"[MediaProcessor] 音频处理完成，原始样本数: {len(audio_np)}, 压缩后样本数: {len(compressed_np)}, 时长: {len(compressed_np)/24000:.2f}s")

            return compressed_np, None, ""
        finally:
            try:
                os.remove(tmp.name)
            except Exception:
                pass

    except Exception as e:
        return None, None, f"音频处理失败: {str(e)}"


def process_document(document_b64: str, document_name: str) -> Tuple[Optional[str], str]:
    """处理文档数据：检查大小、提取文本。

    参数:
        document_b64: base64编码的文档数据（可能包含data URI）
        document_name: 文档名称

    返回:
        (提取的文本或None, 错误信息)
    """
    try:
        import base64 as _b64
        from utils.doc_parser import extract_document_text

        if isinstance(document_b64, str) and "," in document_b64 and document_b64.startswith("data:"):
            document_b64 = document_b64.split(",", 1)[1]

        doc_bytes = _b64.b64decode(document_b64)
        
        ok, msg = check_file_size(doc_bytes, MAX_DOCUMENT_SIZE, "文档")
        if not ok:
            return None, msg

        document_text = extract_document_text(doc_bytes, document_name)
        if not document_text:
            return None, f"文档 '{document_name}' 未能提取文本（可能格式不支持或内容为空）"

        return document_text, ""

    except Exception as e:
        return None, f"文档处理失败: {str(e)}"


try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False