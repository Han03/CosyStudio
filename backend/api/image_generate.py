"""文生图 API 路由。

提供图像生成端点，支持传入提示词生成图像。
"""

import io
import asyncio
import logging
import base64

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from core.model_executor import ModelExecutor

logger = logging.getLogger(__name__)

router = APIRouter()


class GenerateRequest(BaseModel):
    """图像生成请求体。"""
    prompt: str
    num_inference_steps: int = 4
    width: int = 1024
    height: int = 1024
    seed: int = 42


@router.post("/api/image/generate")
async def generate_image(request: GenerateRequest):
    """使用文生图能力生成图像。

    :param request: 生成请求参数
    :return: PNG 格式的图像数据
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="提示词不能为空")

    if request.num_inference_steps < 1 or request.num_inference_steps > 50:
        raise HTTPException(status_code=400, detail="推理步数必须在 1-50 之间")

    if request.width < 256 or request.width > 2048:
        raise HTTPException(status_code=400, detail="图像宽度必须在 256-2048 之间")

    if request.height < 256 or request.height > 2048:
        raise HTTPException(status_code=400, detail="图像高度必须在 256-2048 之间")

    logger.info(
        f"[Image API] 生成图像: prompt='{request.prompt[:50]}...', "
        f"steps={request.num_inference_steps}, size={request.width}x{request.height}, seed={request.seed}"
    )

    executor = ModelExecutor()
    result = await executor.execute_text_to_image(request.prompt)

    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    if result.get("type") == "image" and result.get("data"):
        image_data = base64.b64decode(result["data"])
        return Response(content=image_data, media_type="image/png")

    raise HTTPException(status_code=500, detail="模型生成返回空结果")

__all__ = ["router"]
