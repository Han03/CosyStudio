from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from models.model_capability_manager import capability_manager
from core.model_executor import model_executor
from core.config_manager import get_model_capabilities, get_call_point_models, update_call_point_models
from utils.logger import log_manager
from repositories import (
    add_capability_test,
    get_capability_tests_paged,
    get_capability_test,
    delete_capability_test,
    delete_all_capability_tests,
)

router = APIRouter()
_logger = log_manager.get_logger("model_capability")


class TextPredictRequest(BaseModel):
    prompt: str
    system_prompt: str = ""
    stream: bool = True
    capability_id: Optional[str] = None


class TextToSpeechRequest(BaseModel):
    text: str
    stream: bool = True
    capability_id: Optional[str] = None


class TextToImageRequest(BaseModel):
    prompt: str
    capability_id: Optional[str] = None


class TextToVectorRequest(BaseModel):
    texts: List[str]
    capability_id: Optional[str] = None


class TextRerankRequest(BaseModel):
    query: str
    documents: List[str]
    top_k: int = 5
    capability_id: Optional[str] = None


class CapabilityConfigRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    capability_type: str
    platform_code: str
    model_code: str
    priority: int = 5
    enabled: bool = True
    description: str = ""


@router.get("/api/capabilities/types")
async def get_capability_types():
    """获取所有能力类型"""
    return {"types": capability_manager.get_capability_types()}


@router.get("/api/capabilities/platforms")
async def get_platforms():
    """获取所有平台编码"""
    return {"platforms": capability_manager.get_platform_codes()}


@router.get("/api/capabilities")
async def get_all_capabilities():
    """获取所有模型能力配置"""
    return {"capabilities": capability_manager.get_all_capabilities()}


@router.get("/api/capabilities/test-history")
async def get_test_history(capability_type: str, page: int = 1, page_size: int = 20):
    """分页获取能力测试历史"""
    try:
        result = get_capability_tests_paged(capability_type, page, page_size)
        return result
    except Exception as e:
        _logger.error(f"获取测试历史失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取测试历史失败: {e}")


@router.get("/api/capabilities/history")
async def get_test_history_detail(history_id: int):
    """获取单条测试历史详情"""
    try:
        result = get_capability_test(history_id)
        if not result:
            raise HTTPException(status_code=404, detail="测试记录不存在")
        return {"record": result}
    except Exception as e:
        _logger.error(f"获取测试历史详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取测试历史详情失败: {e}")


@router.delete("/api/capabilities/history")
async def delete_test_history(history_id: int):
    """删除单条测试历史"""
    try:
        success = delete_capability_test(history_id)
        if not success:
            raise HTTPException(status_code=404, detail="测试记录不存在")
        return {"success": True, "message": "测试记录删除成功"}
    except Exception as e:
        _logger.error(f"删除测试历史失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除测试历史失败: {e}")


@router.delete("/api/capabilities/history/clear")
async def clear_test_history(capability_type: str):
    """清空指定能力类型的所有测试历史"""
    try:
        count = delete_all_capability_tests(capability_type)
        return {"success": True, "message": f"已清空 {count} 条测试记录"}
    except Exception as e:
        _logger.error(f"清空测试历史失败: {e}")
        raise HTTPException(status_code=500, detail=f"清空测试历史失败: {e}")


@router.get("/api/capabilities/type")
async def get_capabilities_by_type(capability_type: str):
    """按能力类型获取配置"""
    capabilities = capability_manager.get_capabilities_by_type(capability_type)
    return {"capability_type": capability_type, "capabilities": capabilities}


@router.get("/api/capabilities/best")
async def get_best_capability(capability_type: str):
    """获取优先级最高的能力配置"""
    capability = capability_manager.get_best_capability(capability_type)
    if not capability:
        raise HTTPException(status_code=404, detail="没有可用的能力配置")
    return {"capability": capability}


@router.get("/api/capabilities/detail")
async def get_capability(capability_type: str, capability_id: str):
    """获取指定ID的能力配置"""
    capability = capability_manager.get_capability(capability_type, capability_id)
    if not capability:
        raise HTTPException(status_code=404, detail="能力配置不存在")
    return {"capability": capability}


@router.post("/api/capabilities")
async def add_capability(request: Request):
    """添加能力配置"""
    try:
        data = await request.json()
        capability_type = data.get("capability_type")
        capability = data.get("capability")
        
        if not capability_type or not capability:
            raise HTTPException(status_code=400, detail="缺少capability_type或capability参数")
        
        result = capability_manager.add_capability_config(capability_type, capability)
        return {"success": True, "message": "能力配置添加成功", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _logger.error(f"添加能力配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"添加能力配置失败: {e}")


@router.put("/api/capabilities")
async def update_capability(capability_type: str, capability_id: str, request: Request):
    """更新能力配置"""
    try:
        data = await request.json()
        updates = data.get("updates", {})
        
        result = capability_manager.update_capability_config(capability_type, capability_id, updates)
        return {"success": True, "message": "能力配置更新成功", "result": result}
    except Exception as e:
        _logger.error(f"更新能力配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新能力配置失败: {e}")


@router.delete("/api/capabilities")
async def delete_capability(capability_type: str, capability_id: str):
    """删除能力配置"""
    try:
        result = capability_manager.delete_capability_config(capability_type, capability_id)
        return {"success": True, "message": "能力配置删除成功", "result": result}
    except Exception as e:
        _logger.error(f"删除能力配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除能力配置失败: {e}")


@router.post("/api/capabilities/text-predict")
async def text_predict(request: TextPredictRequest):
    """执行文本预测"""
    try:
        if request.stream:
            async def generate():
                async for chunk in model_executor.execute_text_predict(
                    prompt=request.prompt,
                    system_prompt=request.system_prompt,
                    stream=True,
                    capability_id=request.capability_id
                ):
                    if "error" in chunk:
                        yield f"data: {chunk['error']}\n\n"
                        return
                    yield f"data: {chunk['content']}\n\n"
            
            return StreamingResponse(generate(), media_type="text/event-stream")
        else:
            result = {}
            async for chunk in model_executor.execute_text_predict(
                prompt=request.prompt,
                system_prompt=request.system_prompt,
                stream=False,
                capability_id=request.capability_id
            ):
                result = chunk
            if "error" in result:
                raise HTTPException(status_code=500, detail=result["error"])
            return result
    except Exception as e:
        _logger.error(f"文本预测失败: {e}")
        raise HTTPException(status_code=500, detail=f"文本预测失败: {e}")


@router.post("/api/capabilities/text-to-speech")
async def text_to_speech(request: TextToSpeechRequest):
    """执行语音合成"""
    try:
        if request.stream:
            async def generate():
                async for chunk in model_executor.execute_text_to_speech(
                    text=request.text,
                    stream=True,
                    capability_id=request.capability_id
                ):
                    yield chunk
            
            return StreamingResponse(generate(), media_type="audio/wav")
        else:
            result = b""
            async for chunk in model_executor.execute_text_to_speech(
                text=request.text,
                stream=False,
                capability_id=request.capability_id
            ):
                result = chunk
            return StreamingResponse(result, media_type="audio/wav")
    except Exception as e:
        _logger.error(f"语音合成失败: {e}")
        raise HTTPException(status_code=500, detail=f"语音合成失败: {e}")


@router.post("/api/capabilities/text-to-image")
async def text_to_image(request: TextToImageRequest):
    """执行文生图"""
    try:
        result = await model_executor.execute_text_to_image(
            prompt=request.prompt,
            capability_id=request.capability_id
        )
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except Exception as e:
        _logger.error(f"文生图失败: {e}")
        raise HTTPException(status_code=500, detail=f"文生图失败: {e}")


@router.post("/api/capabilities/text-to-vector")
async def text_to_vector(request: TextToVectorRequest):
    """执行文本转向量"""
    try:
        result = await model_executor.execute_text_to_vector(
            texts=request.texts,
            capability_id=request.capability_id
        )
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except Exception as e:
        _logger.error(f"文本转向量失败: {e}")
        raise HTTPException(status_code=500, detail=f"文本转向量失败: {e}")


@router.post("/api/capabilities/text-rerank")
async def text_rerank(request: TextRerankRequest):
    """执行片段重排序"""
    try:
        result = await model_executor.execute_rerank(
            query=request.query,
            documents=request.documents,
            top_k=request.top_k,
            capability_id=request.capability_id
        )
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except Exception as e:
        _logger.error(f"片段重排序失败: {e}")
        raise HTTPException(status_code=500, detail=f"片段重排序失败: {e}")


# ===================== 测试历史 API =====================

class TestRequest(BaseModel):
    capability_type: str
    capability_id: Optional[str] = None
    input_data: Dict[str, Any]


@router.post("/api/capabilities/test")
async def test_capability(request: TestRequest):
    """测试指定能力"""
    import time
    start_time = time.time()
    try:
        capability_type = request.capability_type
        capability_id = request.capability_id
        input_data = request.input_data

        capability = None
        if capability_id:
            capabilities = get_model_capabilities().get(capability_type, [])
            capability = next((c for c in capabilities if c.get("id") == capability_id), None)
        else:
            capability = capability_manager.get_best_capability(capability_type)

        if not capability:
            raise HTTPException(status_code=404, detail="找不到可用的能力配置")

        platform_code = capability.get("platform_code", "")
        model_code = capability.get("model_code", "")

        output_data = ""
        status = "success"
        error_message = ""

        if capability_type == "text_predict":
            prompt = input_data.get("prompt", "")
            system_prompt = input_data.get("system_prompt", "")
            result = {}
            async for chunk in model_executor.execute_text_predict(
                prompt=prompt,
                system_prompt=system_prompt,
                stream=False,
                capability_id=capability_id
            ):
                result = chunk
            if "error" in result:
                status = "failed"
                error_message = result["error"]
            else:
                output_data = result.get("content", "")
        elif capability_type == "text_to_speech":
            text = input_data.get("text", "")
            result = {}
            audio_chunks = []
            async for chunk in model_executor.execute_text_to_speech(
                text=text,
                stream=False,
                capability_id=capability_id
            ):
                if isinstance(chunk, dict):
                    result = chunk
                    if chunk.get("type") == "pcm_chunk":
                        audio_chunks.append(chunk.get("data", ""))
                    elif chunk.get("type") == "finish":
                        break
                    elif chunk.get("type") == "error":
                        status = "failed"
                        error_message = chunk.get("message", "语音合成失败")
                        break
                else:
                    audio_chunks.append(chunk)
            if status == "success" and audio_chunks:
                output_data = "audio_data"
            elif status == "success":
                status = "failed"
                error_message = "未获取到音频数据"
        elif capability_type == "text_to_image":
            prompt = input_data.get("prompt", "")
            result = await model_executor.execute_text_to_image(
                prompt=prompt,
                capability_id=capability_id
            )
            if "error" in result:
                status = "failed"
                error_message = result["error"]
            else:
                output_data = result.get("image_url", "")
        elif capability_type == "text_to_vector":
            texts = input_data.get("texts", [])
            result = await model_executor.execute_text_to_vector(
                texts=texts,
                capability_id=capability_id
            )
            if "error" in result:
                status = "failed"
                error_message = result["error"]
            else:
                output_data = str(len(result.get("vectors", [])) if result else 0) + " vectors"
        elif capability_type == "text_rerank":
            query = input_data.get("query", "")
            documents = input_data.get("documents", [])
            top_k = int(input_data.get("top_k", 5) or 5)
            result = await model_executor.execute_rerank(
                query=query,
                documents=documents,
                top_k=top_k,
                capability_id=capability_id
            )
            if "error" in result:
                status = "failed"
                error_message = result["error"]
            else:
                output_data = str(len(result.get("results", []) if result else 0)) + " reranked"
        else:
            raise HTTPException(status_code=400, detail=f"未知的能力类型: {capability_type}")

        duration = time.time() - start_time
        add_capability_test(
            capability_type=capability_type,
            capability_id=capability_id or capability.get("id", ""),
            platform_code=platform_code,
            model_code=model_code,
            input_data=str(input_data),
            output_data=output_data,
            status=status,
            error_message=error_message,
            duration=duration,
        )

        return {
            "success": True,
            "capability_id": capability.get("id"),
            "platform_code": platform_code,
            "model_code": model_code,
            "result": result,
            "duration": round(duration, 2),
            "status": status,
        }
    except Exception as e:
        duration = time.time() - start_time
        _logger.error(f"能力测试失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "duration": round(duration, 2),
            "status": "failed",
        }


# ===================== 排序更新 API =====================

class ReorderRequest(BaseModel):
    capability_type: str
    capability_ids: List[str]


@router.post("/api/capabilities/reorder")
async def reorder_capabilities(request: ReorderRequest):
    """重新排序能力配置"""
    try:
        result = capability_manager.reorder_capabilities(
            request.capability_type,
            request.capability_ids
        )
        return {"success": True, "message": "排序更新成功", "result": result}
    except Exception as e:
        _logger.error(f"排序更新失败: {e}")
        raise HTTPException(status_code=500, detail=f"排序更新失败: {e}")


# ===================== 调用点模型配置 API =====================

# 调用点按业务分类组织，每个分类内按执行顺序排列
CALL_POINT_CATEGORIES = [
    {
        "category": "深度初始化",
        "icon": "fas fa-seedling",
        "color": "#6c5ce7",
        "call_points": {
            "init_ai_all_in_one": {"name": "一键全量生成", "description": "深度初始化-一键模式: 一次性生成3套完整方案"},
            "init_ai_project": {"name": "项目定位生成", "description": "深度初始化-步骤2: 项目定位 AI 辅助生成"},
            "init_ai_protagonist": {"name": "主角设定生成", "description": "深度初始化-步骤3: 主角设定 AI 辅助生成"},
            "init_ai_golden_finger": {"name": "金手指设定生成", "description": "深度初始化-步骤4: 金手指设定 AI 辅助生成"},
            "init_ai_world": {"name": "世界观设定生成", "description": "深度初始化-步骤5: 世界观设定 AI 辅助生成"},
            "init_ai_constraints": {"name": "约束包生成", "description": "深度初始化-步骤6: 创意约束包 AI 辅助生成"},
            "story_system": {"name": "故事系统", "description": "Story System 合同生成"},
            "init_executor": {"name": "世界观设定", "description": "世界观、力量体系、金手指等设定"},
            "character_builder": {"name": "角色构建", "description": "角色设定"},
            "plan_executor": {"name": "卷纲规划", "description": "卷纲规划、章节规划"},
        },
    },
    {
        "category": "智能创作",
        "icon": "fas fa-pen-fancy",
        "color": "#00b894",
        "call_points": {
            "chapter_splitter": {"name": "章节拆分", "description": "章节内容拆分"},
            "timeline_fixer": {"name": "时间线修复", "description": "时间线一致性修复"},
            "context_builder": {"name": "上下文构建", "description": "写作上下文构建"},
            "chapter_plot_generator": {"name": "剧情生成", "description": "章节剧情列表"},
            "chapter_plot_reviewer_score": {"name": "剧情审查评分", "description": "剧情多维度质量评分"},
            "chapter_plot_reviewer_revise": {"name": "剧情审查修正", "description": "根据评分反馈修正剧情"},
            "draft_generator": {"name": "草稿生成", "description": "章节草稿正文创作"},
            "draft_reviewer_score": {"name": "草稿审查评分", "description": "草稿多维度质量评分"},
            "draft_reviewer_revise": {"name": "草稿审查修正", "description": "根据评分反馈修正草稿"},
            "draft_polisher": {"name": "草稿润色", "description": "草稿质量优化润色"},
            "fact_recorder": {"name": "事实记录", "description": "剧情事实提取与记录"},
            "setting_recorder": {"name": "设定记录", "description": "世界观设定提取与记录"},
            "foreshadow_cool_point_extractor": {"name": "伏笔爽点提取", "description": "伏笔和爽点提取"},
        },
    },
    {
        "category": "台词配音",
        "icon": "fas fa-microphone-alt",
        "color": "#e17055",
        "call_points": {
            "script_line_generator": {"name": "台词生成", "description": "章节台词/对白生成"},
            "character_profile_extractor": {"name": "角色属性提取", "description": "推断角色性别/年龄/描述"},
            "agent_matcher": {"name": "智能体匹配", "description": "角色-配音智能体全局匹配"},
        },
    },
    {
        "category": "其他",
        "icon": "fas fa-cogs",
        "color": "#636e72",
        "call_points": {
            "query_executor": {"name": "查询执行", "description": "信息查询"},
        },
    },
]

# 扁平索引：{name: detail} 用于向后兼容的快速查找
CALL_POINT_DETAILS = {}
for _cat in CALL_POINT_CATEGORIES:
    CALL_POINT_DETAILS.update(_cat["call_points"])


class CallPointModelsRequest(BaseModel):
    configs: Dict[str, Any]


@router.get("/api/capabilities/call-points")
async def get_call_points():
    """获取所有调用点（按分类分组）及其当前模型覆盖配置，同时返回可选的 text_predict 能力列表"""
    current_overrides = get_call_point_models()

    # 按分类组织返回
    categories = []
    for cat_def in CALL_POINT_CATEGORIES:
        cat_call_points = []
        for name, detail in cat_def["call_points"].items():
            override = current_overrides.get(name, {})
            cat_call_points.append({
                "name": name,
                "display_name": detail["name"],
                "description": detail["description"],
                "category": cat_def["category"],
                "capability_id": override.get("capability_id", ""),
            })
        categories.append({
            "category": cat_def["category"],
            "icon": cat_def["icon"],
            "color": cat_def["color"],
            "call_points": cat_call_points,
        })

    # 返回可选的 text_predict 能力列表供前端下拉选择
    all_capabilities = get_model_capabilities()
    available_capabilities = [
        {"id": cap["id"], "description": cap.get("description") or cap.get("model_code", ""),
         "platform_code": cap.get("platform_code", ""), "model_code": cap.get("model_code", ""),
         "enabled": cap.get("enabled", False)}
        for cap in all_capabilities.get("text_predict", [])
        if cap.get("enabled", False)
    ]
    return {"categories": categories, "available_capabilities": available_capabilities}


@router.post("/api/capabilities/call-points")
async def save_call_points(request: CallPointModelsRequest):
    """批量保存调用点模型覆盖配置"""
    try:
        result = update_call_point_models(request.configs)
        return {"success": True, "message": "调用点配置保存成功", "configs": result.get("call_point_models", {})}
    except Exception as e:
        _logger.error(f"保存调用点配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存调用点配置失败: {e}")