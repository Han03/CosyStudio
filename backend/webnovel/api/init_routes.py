import json
import asyncio
import threading
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from repositories import get_script
from repositories.script_repository import update_script
from utils.logger import log_manager
from utils.llm_json_parser import parse_llm_json

_init_logger = log_manager.get_logger("webnovel_init")
from webnovel.repositories import (
    create_init_session, get_init_session, update_init_session,
    advance_init_session, complete_init_session, delete_init_session,
    save_step_data, save_relationship_data, save_ai_generated_data, get_all_init_data,
    get_webnovel_project_by_script, delete_webnovel_project_by_script,
    get_completed_init_session
)
from webnovel.pipeline.executors.init_executor import InitExecutor
from core.model_executor import get_model_executor
from infrastructure.websocket_broadcast import ws_broadcast_manager

router = APIRouter(prefix="/api/books/scripts/webnovel/init")

# 初始化任务管理：script_id -> {"interrupted": bool, "lock": Lock}
_init_tasks: Dict[int, dict] = {}
_init_tasks_lock = threading.Lock()


def _set_interrupted(script_id: int):
    with _init_tasks_lock:
        if script_id in _init_tasks:
            _init_tasks[script_id]["interrupted"] = True


def _is_interrupted(script_id: int) -> bool:
    with _init_tasks_lock:
        task = _init_tasks.get(script_id)
        return bool(task and task.get("interrupted", False))


def _register_init_task(script_id: int):
    with _init_tasks_lock:
        _init_tasks[script_id] = {"interrupted": False}


def _unregister_init_task(script_id: int):
    with _init_tasks_lock:
        _init_tasks.pop(script_id, None)


class SessionCreateRequest(BaseModel):
    script_id: int


class StepDataRequest(BaseModel):
    script_id: int
    step: int
    data: Dict[str, Any]


class AIGenerateRequest(BaseModel):
    script_id: int
    step: int
    current_data: Dict[str, Any]


class ConfirmRequest(BaseModel):
    script_id: int


@router.post("/session")
def create_init_session_endpoint(data: SessionCreateRequest):
    script = get_script(data.script_id)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    # 支持重复初始化：不再阻止已初始化项目创建会话

    session = get_init_session(data.script_id)
    if session:
        return {"success": True, "session_id": session["id"], "current_step": session["current_step"]}

    # 检查是否有已完成的旧会话（重复初始化场景）：复用并重置，保留历史数据供前端回填
    completed_session = get_completed_init_session(data.script_id)
    if completed_session:
        update_init_session(completed_session["id"], status="active", current_step=2)
        return {"success": True, "session_id": completed_session["id"], "current_step": 2}

    session = create_init_session(data.script_id)
    return {"success": True, "session_id": session["id"], "current_step": session["current_step"]}


@router.get("/session")
def get_init_session_endpoint(script_id: int):
    session = get_init_session(script_id)
    if not session:
        return {"success": False, "message": "没有活跃的初始化会话"}

    all_data = get_all_init_data(session["id"])
    return {
        "success": True,
        "session_id": session["id"],
        "current_step": session["current_step"],
        "status": session["status"],
        "data": all_data
    }


@router.post("/step/{step}")
def save_step_endpoint(step: int, data: StepDataRequest):
    session = get_init_session(data.script_id)
    if not session:
        raise HTTPException(status_code=400, detail="没有活跃的初始化会话")

    if session["current_step"] < step:
        raise HTTPException(status_code=400, detail=f"当前步骤是{session['current_step']}，无法保存步骤{step}")

    step_data = data.data
    if step == 3 and "relationship" in step_data:
        relationship_data = step_data.pop("relationship", {})
        save_relationship_data(session["id"], relationship_data)

    save_step_data(session["id"], step, step_data)

    next_step = step + 1
    if next_step <= 6:
        advance_init_session(session["id"], next_step)
        return {"success": True, "current_step": next_step, "message": f"步骤{step}已保存，进入步骤{next_step}"}
    else:
        return {"success": True, "current_step": 7, "message": f"步骤{step}已保存，进入确认步骤"}


@router.post("/ai/generate/{step}")
async def ai_generate_endpoint(step: int, data: AIGenerateRequest):
    session = get_init_session(data.script_id)
    if not session:
        raise HTTPException(status_code=400, detail="没有活跃的初始化会话")

    try:
        executor = get_model_executor()
        genre = data.current_data.get("project", {}).get("genre", "") or data.current_data.get("genre", "")

        prompts = {
            2: _get_project_prompt,
            3: _get_protagonist_prompt,
            4: _get_golden_finger_prompt,
            5: _get_world_prompt,
            6: _get_constraints_prompt
        }

        prompt_fn = prompts.get(step)
        if not prompt_fn:
            raise HTTPException(status_code=400, detail=f"步骤{step}不支持AI生成")

        system_prompt, user_prompt = prompt_fn(data.current_data, genre)
        
        _init_logger.info(f"[AI生成] 步骤{step} - 系统提示: {system_prompt[:100]}...")
        _init_logger.info(f"[AI生成] 步骤{step} - 用户提示: {user_prompt[:100]}...")

        # 🔴 提前解析 project_id，确保 execute_text_chat 统一入口写日志时能关联到项目
        # （如果等到 parse_llm_json 阶段才解析，统一入口那条日志的 script_id/project_id 会是空/0）
        project_id = 0
        try:
            from webnovel.repositories import get_webnovel_project_by_script
            _proj = get_webnovel_project_by_script(data.script_id)
            if _proj:
                project_id = _proj.get("id", 0)
        except Exception:
            pass

        import time as _time
        _call_start = _time.time()
        # 🔴 必须把 script_id / project_id / executor_name / prompt_name 传进 execute_text_chat，
        # 否则 model_executor 统一入口的兜底日志（finally 块中写的那条）这些字段全是空值，
        # 用户查日志时按 script_id 过滤完全搜不到创意约束包等步骤的调用记录
        result = await executor.execute_text_chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=4000,
            script_id=data.script_id,
            project_id=project_id,
            executor_name="webnovel_init_api",
            prompt_name=f"step_{step}_ai_generate",
        )
        _latency_ms = int((_time.time() - _call_start) * 1000)

        content = result.get("content", "")
        content = content.strip()

        _init_logger.info(f"[AI生成] 步骤{step} - AI输出: {content[:200]}...")

        if not content:
            _init_logger.error(f"[AI生成] 步骤{step} - AI返回空内容，尝试使用模拟数据")
            if step == 6:
                mock_data = _generate_mock_constraint_packages(data.current_data, genre)
                save_ai_generated_data(session["id"], {f"step_{step}": mock_data})
                return {"success": True, "data": mock_data, "is_packages": True}
            else:
                raise HTTPException(status_code=500, detail="AI生成返回空内容")

        ai_result = parse_llm_json(
            content,
            script_id=data.script_id,
            project_id=project_id,
            executor_name="webnovel_init_api",
            prompt_name=f"step_{step}_ai_generate",
            model_name=result.get("model_name", "") if isinstance(result, dict) else "",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_tokens=result.get("input_tokens", 0) if isinstance(result, dict) else 0,
            output_tokens=result.get("output_tokens", 0) if isinstance(result, dict) else 0,
            latency_ms=_latency_ms,
        )
        
        if ai_result is None:
            _init_logger.error(f"[AI生成] 步骤{step} - JSON解析失败，原始内容: {content[:500]}")
            ai_result = _parse_invalid_json(content)
        
        if step == 6:
            constraint_packages = ai_result.get("constraint_packages", [])
            if constraint_packages:
                _init_logger.info(f"[AI生成] 步骤6 - 生成了{len(constraint_packages)}套创意约束包")
                save_ai_generated_data(session["id"], {f"step_{step}": ai_result})
                return {"success": True, "data": ai_result, "is_packages": True}
        
        for key, value in ai_result.items():
            if isinstance(value, list):
                ai_result[key] = "\n".join(str(item) for item in value)
            elif isinstance(value, dict):
                lines = []
                for k, v in value.items():
                    if isinstance(v, dict):
                        v_str = "\n".join(f"  {sk}: {sv}" for sk, sv in v.items())
                        lines.append(f"{k}: {v_str}")
                    else:
                        lines.append(f"{k}: {v}")
                ai_result[key] = "\n".join(lines)

        save_ai_generated_data(session["id"], {f"step_{step}": ai_result})

        return {"success": True, "data": ai_result}

    except Exception as e:
        _init_logger.error(f"[AI生成] 步骤{step} - AI服务失败，尝试使用模拟数据: {str(e)}")
        if step == 6:
            mock_data = _generate_mock_constraint_packages(data.current_data, genre)
            save_ai_generated_data(session["id"], {f"step_{step}": mock_data})
            return {"success": True, "data": mock_data, "is_packages": True}
        else:
            raise HTTPException(status_code=500, detail=f"AI生成失败: {str(e)}")


def _generate_mock_constraint_packages(current_data: Dict, genre: str) -> Dict:
    title = current_data.get("project", {}).get("title", "测试书名")
    protagonist_name = current_data.get("protagonist", {}).get("name", "主角")
    
    packages = [
        {
            "package_name": f"{title} - 反套路逆袭版",
            "one_liner_selling_point": f"{protagonist_name}并非天生主角，他的金手指需要用寿命兑换，每次变强都是一场赌博",
            "anti_trope_rule": "金手指有不可逆代价：每次使用金手指，主角失去一年寿命",
            "hard_constraints": [
                "主角不能主动攻击任何人，只能防御和反击",
                "金手指每天最多使用3次，每次使用后冷却1小时",
                "世界规则对主角不利，他没有任何主角特权"
            ],
            "protagonist_flaw_driven": f"{protagonist_name}的贪婪让他不断消耗寿命获取力量，最终面临寿命耗尽的危机",
            "antagonist_mirror": f"反派同样拥有寿命兑换金手指，但他选择掠夺他人寿命而非消耗自己",
            "opening_hook": f"{protagonist_name}在濒死之际激活金手指，却发现代价是寿命——他必须在变强和生存之间做出抉择",
            "differentiation": "不同于常规修仙爽文的碾压式升级，本作强调代价与抉择，每次升级都是一场赌博",
            "scoring": {
                "creativity": {"score": 8, "reason": "反套路代价机制设计新颖，不同于传统爽文"},
                "feasibility": {"score": 7, "reason": "写作难度适中，寿命机制容易展开剧情"},
                "market_appeal": {"score": 7, "reason": "题材受众广，但反套路可能不被部分爽文读者接受"},
                "sustainability": {"score": 8, "reason": "寿命机制可长期展开，有无限扩展空间"},
                "emotional_impact": {"score": 8, "reason": "抉择主题容易引发读者共鸣"}
            },
            "three_questions": {
                "q1": "因为反套路代价机制是本故事的核心，必须通过寿命消耗来制造紧张感",
                "q2": "会崩。如果主角换成常规无敌人设，寿命代价机制就失去意义",
                "q3": "可以。'金手指需要寿命兑换'一句话就能讲清且不撞套路"
            }
        },
        {
            "package_name": f"{title} - 智斗博弈版",
            "one_liner_selling_point": f"{protagonist_name}没有任何战斗能力，却凭借智谋和规则理解，在强者林立的世界中生存",
            "anti_trope_rule": "主角无法直接战斗，只能通过理解和利用世界规则来达成目标",
            "hard_constraints": [
                "主角无法修炼任何功法，没有任何战斗能力",
                "主角每次使用规则漏洞，世界会修复该漏洞并产生新规则",
                "主角的知识是他唯一的武器，但知识也可能过时"
            ],
            "protagonist_flaw_driven": f"{protagonist_name}的傲慢让他低估了规则的复杂性，最终被自己发现的规则反噬",
            "antagonist_mirror": f"反派同样精通规则，但他选择破坏规则获取力量，而主角选择理解规则",
            "opening_hook": f"{protagonist_name}发现世界存在规则漏洞，却在利用漏洞时发现自己早已身在规则之中",
            "differentiation": "完全摒弃传统战斗升级模式，采用智斗和规则博弈，强调知识就是力量",
            "scoring": {
                "creativity": {"score": 9, "reason": "完全反套路的智斗设定，在同类作品中非常独特"},
                "feasibility": {"score": 6, "reason": "纯智斗写作难度较高，需要精心设计规则和情节"},
                "market_appeal": {"score": 6, "reason": "受众相对小众，但喜欢智斗的读者粘性高"},
                "sustainability": {"score": 7, "reason": "规则系统可扩展，但需要不断创新规则"},
                "emotional_impact": {"score": 7, "reason": "智斗的爽点在于解谜和博弈，情感共鸣中等"}
            },
            "three_questions": {
                "q1": "因为智斗是本故事的核心，主角必须没有战斗能力才能凸显智谋的重要性",
                "q2": "会崩。如果主角能战斗，智斗设定就失去意义",
                "q3": "可以。'无战斗能力靠智谋生存'一句话就能讲清且不撞套路"
            }
        },
        {
            "package_name": f"{title} - 成长代价版",
            "one_liner_selling_point": f"{protagonist_name}每一次突破都伴随着失去，最强者往往也是最孤独的人",
            "anti_trope_rule": "主角的成长以失去重要的人为代价，每升一级就失去一段关系",
            "hard_constraints": [
                "主角每次突破境界，必须选择遗忘一个重要的人",
                "被遗忘的人会在世界中消失，只有主角记得他们曾经存在",
                "主角最终可能成为最强者，但身边空无一人"
            ],
            "protagonist_flaw_driven": f"{protagonist_name}的执念让他不断追求力量，却在过程中失去了所有在乎的人",
            "antagonist_mirror": f"反派同样经历失去，但他选择让所有人都体会失去的痛苦",
            "opening_hook": f"{protagonist_name}第一次突破后，发现母亲消失了——这才是修炼的真相",
            "differentiation": "不同于传统升级流的收获式成长，本作强调成长的代价和孤独",
            "scoring": {
                "creativity": {"score": 7, "reason": "成长代价设定有新意，但不算特别新颖"},
                "feasibility": {"score": 8, "reason": "写作难度较低，情感线容易展开"},
                "market_appeal": {"score": 8, "reason": "情感主题受众广，容易引发共鸣"},
                "sustainability": {"score": 7, "reason": "失去机制可展开，但需要控制节奏"},
                "emotional_impact": {"score": 9, "reason": "失去主题容易引发强烈的情感共鸣"}
            },
            "three_questions": {
                "q1": "因为成长代价是本故事的核心主题，必须通过失去来探讨力量与代价的关系",
                "q2": "会崩。如果主角没有成长代价，故事的情感核心就不存在",
                "q3": "可以。'每突破一次失去一个人'一句话就能讲清且不撞套路"
            }
        }
    ]
    
    return {"constraint_packages": packages}


class SelectPackageRequest(BaseModel):
    script_id: int
    package_index: int


@router.post("/select-package")
def select_package_endpoint(data: SelectPackageRequest):
    session = get_init_session(data.script_id)
    if not session:
        raise HTTPException(status_code=400, detail="没有活跃的初始化会话")

    all_data = get_all_init_data(session["id"])
    ai_data = all_data.get("ai_generated_data", {})
    step_6_data = ai_data.get("step_6", {})
    constraint_packages = step_6_data.get("constraint_packages", [])
    
    if data.package_index < 0 or data.package_index >= len(constraint_packages):
        raise HTTPException(status_code=400, detail="无效的方案索引")
    
    selected_package = constraint_packages[data.package_index]
    
    constraints_data = {
        "anti_trope": selected_package.get("anti_trope_rule", ""),
        "hard_constraints": selected_package.get("hard_constraints", []),
        "core_selling_points": selected_package.get("one_liner_selling_point", ""),
        "opening_hook": selected_package.get("opening_hook", ""),
        "protagonist_flaw": selected_package.get("protagonist_flaw_driven", ""),
        "villain_mirror": selected_package.get("antagonist_mirror", ""),
        "selected_package_name": selected_package.get("package_name", "")
    }
    
    save_step_data(session["id"], 6, {"constraints": constraints_data})
    
    _init_logger.info(f"[选择方案] 步骤6 - 用户选择了方案: {selected_package.get('package_name', '')}")
    
    return {"success": True, "data": constraints_data}


@router.post("/confirm")
async def confirm_init_endpoint(data: ConfirmRequest):
    session = get_init_session(data.script_id)
    if not session:
        raise HTTPException(status_code=400, detail="没有活跃的初始化会话")

    script = get_script(data.script_id)
    if not script:
        raise HTTPException(status_code=404, detail="剧本不存在")

    if script.get("status") == "initializing":
        raise HTTPException(status_code=400, detail="项目正在初始化中，请勿重复提交")

    # ============= 容错与重复初始化：清理旧数据 =============
    script_status = script.get("status") or ""
    existing_project = get_webnovel_project_by_script(data.script_id)
    if existing_project:
        # 重复初始化：清除旧项目数据，允许重新执行
        delete_webnovel_project_by_script(data.script_id)
        _init_logger.info(
            f"[深度初始化] script_id={data.script_id} 检测到已有项目，清理后重新初始化"
        )
    elif script_status == "failed":
        # 上次初始化失败：可能残留了 webnovel_project 记录，清理干净
        delete_webnovel_project_by_script(data.script_id)

    _register_init_task(data.script_id)
    update_script(data.script_id, status="initializing", progress_message="深度初始化中")

    asyncio.create_task(_run_init_async(data.script_id, session["id"]))

    return {"success": True, "message": "初始化任务已启动，请通过WebSocket查看进度"}


async def _run_init_async(script_id: int, session_id: int):
    """异步执行深度初始化任务，通过WebSocket广播进度。"""
    async def progress_callback(step: str, message: str, progress: int):
        await ws_broadcast_manager.broadcast_init_progress(
            script_id, "running", step, message, progress
        )

    def interrupt_check():
        return _is_interrupted(script_id)

    try:
        all_data = get_all_init_data(session_id)
        project_data = _merge_all_data(all_data)

        executor = InitExecutor(script_id, 0, session_id,
                                progress_callback=progress_callback,
                                interrupt_check=interrupt_check)
        result = await executor.execute({"project_data": project_data})

        if result.success:
            complete_init_session(session_id)
            update_script(script_id, status="ready", progress_message="深度初始化完成")
            await ws_broadcast_manager.broadcast_init_progress(
                script_id, "completed", "completed", "深度初始化完成", 100
            )
            _init_logger.info(f"[深度初始化] script_id={script_id} 完成")
        else:
            update_script(script_id, status="failed", progress_message=result.error_message)
            await ws_broadcast_manager.broadcast_init_progress(
                script_id, "failed", "failed", result.error_message or "初始化失败", 0
            )
            _init_logger.error(f"[深度初始化] script_id={script_id} 失败: {result.error_message}")
    except Exception as e:
        _init_logger.error(f"[深度初始化] script_id={script_id} 异常: {e}")
        update_script(script_id, status="failed", progress_message=f"初始化异常: {str(e)}")
        await ws_broadcast_manager.broadcast_init_progress(
            script_id, "failed", "failed", f"初始化异常: {str(e)}", 0
        )
    finally:
        _unregister_init_task(script_id)


@router.post("/interrupt")
def interrupt_init_endpoint(data: ConfirmRequest):
    """中断正在进行的深度初始化任务。

    若服务器重启导致任务丢失但剧本状态仍为initializing，也允许重置状态。
    """
    with _init_tasks_lock:
        task = _init_tasks.get(data.script_id)

    if task:
        _set_interrupted(data.script_id)
        _init_logger.info(f"[深度初始化] script_id={data.script_id} 用户请求中断")
    else:
        script = get_script(data.script_id)
        if script and script.get("status") == "initializing":
            _init_logger.warning(f"[深度初始化] script_id={data.script_id} 任务不存在但状态为initializing，强制重置")
        else:
            raise HTTPException(status_code=400, detail="没有正在进行的初始化任务")

    update_script(data.script_id, status="failed", progress_message="初始化已中断")
    return {"success": True, "message": "中断请求已发送"}


@router.get("/status")
def get_init_status_endpoint(script_id: int):
    """查询初始化任务状态。"""
    with _init_tasks_lock:
        task = _init_tasks.get(script_id)
    script = get_script(script_id)
    is_running = bool(task)
    return {
        "success": True,
        "is_running": is_running,
        "status": script.get("status") if script else "unknown",
        "progress_message": script.get("progress_message", "") if script else "",
    }


@router.post("/cancel")
def cancel_init_endpoint(script_id: int):
    session = get_init_session(script_id)
    if not session:
        raise HTTPException(status_code=400, detail="没有活跃的初始化会话")

    delete_init_session(session["id"])
    return {"success": True, "message": "初始化会话已取消"}


def _merge_all_data(all_data: Dict) -> Dict:
    merged = {}
    
    project_data = all_data.get("project_data", {})
    if isinstance(project_data, dict):
        if "project" in project_data:
            project_data = project_data["project"]
        merged.update(project_data)
    
    protagonist_data = all_data.get("protagonist_data", {})
    if isinstance(protagonist_data, dict):
        if "protagonist" in protagonist_data:
            protagonist_data = protagonist_data["protagonist"]
        merged["protagonist"] = protagonist_data
        merged["protagonist_name"] = protagonist_data.get("name", "")
        merged["protagonist_desire"] = protagonist_data.get("desire", "")
        merged["protagonist_flaw"] = protagonist_data.get("flaw", "")
        merged["protagonist_archetype"] = protagonist_data.get("archetype", "")
        merged["protagonist_structure"] = protagonist_data.get("structure", "单主角")
    
    relationship_data = all_data.get("relationship_data", {})
    if isinstance(relationship_data, dict):
        if "relationship" in relationship_data:
            relationship_data = relationship_data["relationship"]
        merged["relationship"] = relationship_data
        merged["heroine_config"] = relationship_data.get("heroine_config", "")
        merged["heroine_names"] = relationship_data.get("heroine_names", "")
        merged["heroine_role"] = relationship_data.get("heroine_role", "")
        merged["antagonist_level"] = relationship_data.get("antagonist_level", "")
        merged["antagonist_tiers"] = relationship_data.get("antagonist_tiers", "")
    
    golden_finger_data = all_data.get("golden_finger_data", {})
    if isinstance(golden_finger_data, dict):
        if "golden_finger" in golden_finger_data:
            golden_finger_data = golden_finger_data["golden_finger"]
        merged["golden_finger"] = golden_finger_data
        merged["golden_finger_type"] = golden_finger_data.get("type", "")
        merged["golden_finger_name"] = golden_finger_data.get("name", "")
        merged["golden_finger_style"] = golden_finger_data.get("style", "")
        merged["gf_visibility"] = golden_finger_data.get("visibility", "")
        merged["gf_irreversible_cost"] = golden_finger_data.get("irreversible_cost", "")
    
    world_data = all_data.get("world_data", {})
    if isinstance(world_data, dict):
        if "world" in world_data:
            world_data = world_data["world"]
        merged["worldview"] = world_data
        merged["world_scale"] = world_data.get("scale", "") or world_data.get("worldview_level", "")
        merged["power_system_type"] = world_data.get("power_system_type", "") or world_data.get("power_system", "")
        merged["factions"] = world_data.get("factions", "")
        merged["social_class"] = world_data.get("social_class", "")
        merged["currency_system"] = world_data.get("currency_system", "")
        merged["sect_hierarchy"] = world_data.get("sect_hierarchy", "")
        merged["cultivation_chain"] = world_data.get("cultivation_chain", "")
    
    constraints_data = all_data.get("constraints_data", {})
    if isinstance(constraints_data, dict):
        if "constraints" in constraints_data:
            constraints_data = constraints_data["constraints"]
        merged["constraints"] = constraints_data
        
        anti_trope_rules = constraints_data.get("anti_trope", "")
        if isinstance(anti_trope_rules, list):
            anti_trope_rules = "\n".join(anti_trope_rules)
        merged["anti_trope_rules"] = anti_trope_rules
        
        hard_constraints = constraints_data.get("hard_constraints", "")
        if isinstance(hard_constraints, list):
            hard_constraints = "\n".join(hard_constraints)
        merged["hard_constraints"] = hard_constraints
        
        core_selling_points = constraints_data.get("core_selling_points", "")
        if isinstance(core_selling_points, list):
            core_selling_points = "\n".join(core_selling_points)
        merged["core_selling_points"] = core_selling_points
        
        opening_hook = constraints_data.get("opening_hook", "")
        if isinstance(opening_hook, list):
            opening_hook = "\n".join(opening_hook)
        merged["opening_hook"] = opening_hook

        protagonist_flaw = constraints_data.get("protagonist_flaw", "")
        if isinstance(protagonist_flaw, list):
            protagonist_flaw = "\n".join(protagonist_flaw)
        if protagonist_flaw:
            merged["protagonist_flaw"] = protagonist_flaw

        villain_mirror = constraints_data.get("villain_mirror", "")
        if isinstance(villain_mirror, list):
            villain_mirror = "\n".join(villain_mirror)
        if villain_mirror:
            merged["villain_mirror"] = villain_mirror

    ai_data = all_data.get("ai_generated_data", {})
    for step_key, step_data in ai_data.items():
        if isinstance(step_data, dict):
            for key, value in step_data.items():
                if isinstance(value, list):
                    if any(isinstance(item, dict) for item in value):
                        continue
                    value = "\n".join(str(item) for item in value)
                elif isinstance(value, dict):
                    continue
                if key not in merged or not merged[key]:
                    merged[key] = value

    return merged


def _get_project_prompt(current_data: Dict, genre: str) -> tuple:
    system_prompt = "你是一位拥有10年经验的顶级网文编辑和创意策划师。"
    
    project = current_data.get('project', current_data)
    title = project.get('title', '')
    existing_one_liner = project.get('one_liner', '')
    existing_core_conflict = project.get('core_conflict', '')
    
    user_prompt = f"""请为以下网文项目生成项目基础信息。

【已知信息】
书名：{title}
题材：{genre}

【用户已填信息】
一句话故事：{existing_one_liner if existing_one_liner else '未填写'}
核心冲突：{existing_core_conflict if existing_core_conflict else '未填写'}

【生成要求】
请根据已知信息和用户已填信息，生成或完善以下字段：
- one_liner: 一句话故事（必须能一句话讲清且不撞模板）
- core_conflict: 核心冲突
- target_words: 目标字数（数字）
- target_chapters: 目标章节（数字）
- target_reader: 目标读者
- platform: 目标平台

注意：如果用户已填写某个字段，请保留或基于用户输入进行优化；如果用户未填写，则根据题材和书名进行创作。

【输出格式】JSON格式，只输出上述字段。"""
    return system_prompt, user_prompt


def _get_protagonist_prompt(current_data: Dict, genre: str) -> tuple:
    system_prompt = "你是一位专业的网文角色设计师，擅长设计角色关系和冲突。"
    
    project = current_data.get('project', current_data)
    protagonist = current_data.get('protagonist', {})
    
    user_prompt = f"""请为以下网文项目生成主角设定和反派镜像。

【项目信息】
书名：{project.get('title', '')}
题材：{genre}
一句话故事：{project.get('one_liner', '')}
核心冲突：{project.get('core_conflict', '')}

【用户已填主角信息】
主角姓名：{protagonist.get('name', '') if protagonist.get('name', '') else '未填写'}
主角欲望：{protagonist.get('desire', '') if protagonist.get('desire', '') else '未填写'}
主角缺陷：{protagonist.get('flaw', '') if protagonist.get('flaw', '') else '未填写'}
主角原型：{protagonist.get('archetype', '') if protagonist.get('archetype', '') else '未填写'}
反派镜像：{protagonist.get('villain_mirror', '') if protagonist.get('villain_mirror', '') else '未填写'}

【生成要求】
请根据项目信息和用户已填信息，生成或完善以下字段：
- name: 主角姓名
- desire: 主角欲望（最想要的是什么）
- flaw: 主角缺陷（会导致主角付出代价的缺陷）
- archetype: 主角原型（如：废柴逆袭、重生归来、隐世传承）
- structure: 主角结构（单主角/多主角）
- villain_mirror: 反派镜像（一句话描述反派与主角的对抗关系，如"主角追求自由，反派代表秩序"）

注意：如果用户已填写某个字段，请保留或基于用户输入进行优化；如果用户未填写，则根据项目信息进行创作。

【输出格式】JSON格式，只输出上述字段。"""
    return system_prompt, user_prompt


def _get_golden_finger_prompt(current_data: Dict, genre: str) -> tuple:
    system_prompt = "你是一位专业的网文金手指设计师。"
    
    project = current_data.get('project', current_data)
    protagonist = current_data.get('protagonist', {})
    golden_finger = current_data.get('golden_finger', {})
    
    user_prompt = f"""请为以下网文项目设计金手指。

【项目信息】
书名：{project.get('title', '')}
题材：{genre}
一句话故事：{project.get('one_liner', '')}
核心冲突：{project.get('core_conflict', '')}
主角姓名：{protagonist.get('name', '')}
主角欲望：{protagonist.get('desire', '')}
主角缺陷：{protagonist.get('flaw', '')}

【用户已填金手指信息】
金手指类型：{golden_finger.get('type', '') if golden_finger.get('type', '') else '未填写'}
金手指名称：{golden_finger.get('name', '') if golden_finger.get('name', '') else '未填写'}
金手指风格：{golden_finger.get('style', '') if golden_finger.get('style', '') else '未填写'}
可见度：{golden_finger.get('visibility', '') if golden_finger.get('visibility', '') else '未填写'}
不可逆代价：{golden_finger.get('irreversible_cost', '') if golden_finger.get('irreversible_cost', '') else '未填写'}

【生成要求】
请根据项目信息和用户已填信息，生成或完善以下字段：
- type: 金手指类型（无金手指/系统/传承/法宝/血脉/功法/重生/其他）
- name: 金手指名称（无则留空）
- style: 风格（辅助型/战斗型/经营型/信息流）
- visibility: 可见度（隐藏/半透明/公开）
- irreversible_cost: 不可逆代价（必须有代价或明确"无+理由"）
- growth_rhythm: 成长节奏

注意：如果用户已填写某个字段，请保留或基于用户输入进行优化；如果用户未填写，则根据项目信息和主角设定进行创作。

【输出格式】JSON格式，只输出上述字段。"""
    return system_prompt, user_prompt


def _get_world_prompt(current_data: Dict, genre: str) -> tuple:
    system_prompt = "你是一位专业的网文世界观设计师。"
    
    project = current_data.get('project', current_data)
    protagonist = current_data.get('protagonist', {})
    golden_finger = current_data.get('golden_finger', {})
    world = current_data.get('world', {})
    
    user_prompt = f"""请为以下网文项目设计世界观。

【项目信息】
书名：{project.get('title', '')}
题材：{genre}
一句话故事：{project.get('one_liner', '')}
核心冲突：{project.get('core_conflict', '')}
主角姓名：{protagonist.get('name', '')}
主角欲望：{protagonist.get('desire', '')}
金手指类型：{golden_finger.get('type', '')}
金手指名称：{golden_finger.get('name', '')}

【用户已填世界观信息】
世界观复杂度：{world.get('worldview_level', '') if world.get('worldview_level', '') else '未填写'}
力量体系：{world.get('power_system', '') if world.get('power_system', '') else '未填写'}
地理设定：{world.get('geography', '') if world.get('geography', '') else '未填写'}
历史背景：{world.get('history', '') if world.get('history', '') else '未填写'}
关键地点：{world.get('key_locations', '') if world.get('key_locations', '') else '未填写'}

【生成要求】
请根据项目信息和用户已填信息，生成或完善以下字段：
- scale: 世界规模（单城/多城/大陆/多界）- 必须是这四个值之一
- power_system_type: 力量体系类型（修仙/武道/魔法/科技/异能/职场/无）- 必须是这七个值之一
- factions: 势力格局 - 用换行分隔的字符串，不要用数组
- social_class: 社会阶层与资源分配 - 用换行分隔的字符串，不要用数组
- currency_system: 货币体系（如适用）- 用换行分隔的字符串，不要用数组
- cultivation_chain: 境界链（如适用）- 用换行分隔的字符串，如"炼气-筑基-金丹-元婴"，不要用数组
- sect_hierarchy: 宗门/组织层级（如适用）- 用换行分隔的字符串，不要用数组

注意：如果用户已填写某个字段，请保留或基于用户输入进行优化；如果用户未填写，则根据项目信息、主角设定和金手指进行创作。所有字段必须是字符串类型，不要使用数组或对象。

【输出格式】JSON格式，只输出上述字段，所有值都是字符串。"""
    return system_prompt, user_prompt


def _get_constraints_prompt(current_data: Dict, genre: str) -> tuple:
    system_prompt = "你是一位拥有10年经验的顶级网文编辑和创意策划师，擅长为网文项目设计独特的创意约束和卖点定位。"
    
    project = current_data.get('project', current_data)
    protagonist = current_data.get('protagonist', {})
    golden_finger = current_data.get('golden_finger', {})
    world = current_data.get('world', {})
    constraints = current_data.get('constraints', {})
    
    user_prompt = f"""请为以下网文项目设计2-3套创意约束包方案。

【项目信息】
书名：{project.get('title', '')}
题材：{genre}
一句话故事：{project.get('one_liner', '')}
核心冲突：{project.get('core_conflict', '')}
主角姓名：{protagonist.get('name', '')}
主角欲望：{protagonist.get('desire', '')}
主角缺陷：{protagonist.get('flaw', '')}
金手指类型：{golden_finger.get('type', '')}
金手指名称：{golden_finger.get('name', '')}
世界规模：{world.get('scale', '') or world.get('worldview_level', '')}
力量体系类型：{world.get('power_system_type', '') or world.get('power_system', '')}

【用户已填约束信息】
单章字数：{constraints.get('word_count_chapter', '') if constraints.get('word_count_chapter', '') else '未填写'}
是否序言：{constraints.get('prologue', '') if constraints.get('prologue', '') else '未填写'}
第一章设计：{constraints.get('first_chapter', '') if constraints.get('first_chapter', '') else '未填写'}
文风：{constraints.get('style', '') if constraints.get('style', '') else '未填写'}
套路清单：{constraints.get('tropes', '') if constraints.get('tropes', '') else '未填写'}

【生成要求】
为这个项目生成3套创意约束包，每套包含：
1. package_name: 方案名称（简洁有力）
2. one_liner_selling_point: 一句话卖点（必须能一句话讲清且不撞模板）
3. anti_trope_rule: 反套路规则1条（与常规题材写法形成反差）
4. hard_constraints: 硬约束2-3条（必须遵守的硬性规则，增加故事张力）
5. protagonist_flaw_driven: 主角缺陷驱动一句话（缺陷如何导致主角付出代价）
6. antagonist_mirror: 反派镜像一句话（反派与主角的镜像关系）
7. opening_hook: 开篇钩子（吸引读者继续阅读的开篇设计）
8. differentiation: 差异化说明（与同类作品的区别）
9. scoring: 五维评分（每项1-10分，含理由）：
   - creativity: 创意独特性
   - feasibility: 落地可行性
   - market_appeal: 市场吸引力
   - sustainability: 长线可持续性
   - emotional_impact: 情感冲击力
10. three_questions: 三问筛选答案：
    - q1: 为什么这题材必须这么写？
    - q2: 换常规主角会不会塌？
    - q3: 卖点能否一句话讲清且不撞模板？

【三问筛选】
每套方案必须回答上述三个问题。

注意：如果用户已填写某个字段，请保留或基于用户输入进行优化；如果用户未填写，则根据项目信息、主角设定、金手指和世界观进行创作。

【输出格式】JSON格式，包含constraint_packages数组。示例格式：
{{
    "constraint_packages": [
        {{
            "package_name": "方案A：xxx",
            "one_liner_selling_point": "xxx",
            "anti_trope_rule": "xxx",
            "hard_constraints": ["xxx", "xxx"],
            "protagonist_flaw_driven": "xxx",
            "antagonist_mirror": "xxx",
            "opening_hook": "xxx",
            "differentiation": "xxx",
            "scoring": {{
                "creativity": {{ "score": 8, "reason": "xxx" }},
                "feasibility": {{ "score": 7, "reason": "xxx" }},
                "market_appeal": {{ "score": 9, "reason": "xxx" }},
                "sustainability": {{ "score": 7, "reason": "xxx" }},
                "emotional_impact": {{ "score": 8, "reason": "xxx" }}
            }},
            "three_questions": {{
                "q1": "xxx",
                "q2": "xxx",
                "q3": "xxx"
            }}
        }}
    ]
}}"""
    return system_prompt, user_prompt


def _parse_invalid_json(content: str) -> dict:
    result = {}
    try:
        import re
        pattern = r'"([^"]+)":\s*(\[[^]]*\]|\{[^}]*\}|"[^"]*"|[\d.]+|[^,\n}]+)'
        matches = re.findall(pattern, content)
        
        for key, value in matches:
            value = value.strip()
            if value.startswith('[') and value.endswith(']'):
                try:
                    arr = json.loads(value)
                    result[key] = "\n".join(str(item) for item in arr)
                except:
                    result[key] = value.replace('\n', ' ')
            elif value.startswith('{') and value.endswith('}'):
                try:
                    obj = json.loads(value)
                    lines = []
                    for k, v in obj.items():
                        if isinstance(v, dict):
                            v_str = "\n".join(f"  {sk}: {sv}" for sk, sv in v.items())
                            lines.append(f"{k}: {v_str}")
                        else:
                            lines.append(f"{k}: {v}")
                    result[key] = "\n".join(lines)
                except:
                    result[key] = value.replace('\n', ' ')
            elif value.startswith('"') and value.endswith('"'):
                result[key] = value[1:-1]
            else:
                result[key] = value
    except Exception as e:
        _init_logger.warning(f"解析无效JSON失败: {e}")
        result = {"raw_content": content[:500]}
    
    return result