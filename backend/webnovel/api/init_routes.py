import json
import os
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
        
        # ── 多选项模式：步骤 2-5 返回 3 套方案 ──
        if "options" in ai_result and isinstance(ai_result["options"], list):
            _init_logger.info(f"[AI生成] 步骤{step} - 生成{len(ai_result['options'])}套方案")
            save_ai_generated_data(session["id"], {f"step_{step}": ai_result})
            return {"success": True, "data": ai_result, "is_multi_options": True}
        
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
    packages = [
        {
            "anti_trope_rule": "金手指有不可逆代价：每次使用金手指，主角失去一年寿命",
            "hard_constraints": [
                "主角不能主动攻击任何人，只能防御和反击",
                "金手指每天最多使用3次，每次使用后冷却1小时",
                "世界规则对主角不利，他没有任何主角特权"
            ],
            "core_selling_points": "每次变强都是一场赌博，代价与抉择构成故事核心张力",
            "opening_hook": "主角在濒死之际激活金手指，却发现代价是寿命——他必须在变强和生存之间做出抉择"
        },
        {
            "anti_trope_rule": "主角无法直接战斗，只能通过理解和利用世界规则来达成目标",
            "hard_constraints": [
                "主角无法修炼任何功法，没有任何战斗能力",
                "主角每次使用规则漏洞，世界会修复该漏洞并产生新规则",
                "主角的知识是他唯一的武器，但知识也可能过时"
            ],
            "core_selling_points": "完全摒弃传统战斗升级模式，采用智斗和规则博弈，强调知识就是力量",
            "opening_hook": "主角发现世界存在规则漏洞，却在利用漏洞时发现自己早已身在规则之中"
        },
        {
            "anti_trope_rule": "主角的成长以失去重要的人为代价，每升一级就失去一段关系",
            "hard_constraints": [
                "主角每次突破境界，必须选择遗忘一个重要的人",
                "被遗忘的人会在世界中消失，只有主角记得他们曾经存在",
                "主角最终可能成为最强者，但身边空无一人"
            ],
            "core_selling_points": "不同于传统升级流的收获式成长，本作强调成长的代价和孤独",
            "opening_hook": "主角第一次突破后，发现母亲消失了——这才是修炼的真相"
        }
    ]
    
    return {"constraint_packages": packages}


class SelectOptionRequest(BaseModel):
    script_id: int
    step: int
    option_index: int


@router.post("/select-option")
def select_option_endpoint(data: SelectOptionRequest):
    """通用方案选择端点：步骤 2-5 用户从 AI 生成的 3 套方案中选择一套。"""
    session = get_init_session(data.script_id)
    if not session:
        raise HTTPException(status_code=400, detail="没有活跃的初始化会话")

    all_data = get_all_init_data(session["id"])
    ai_data = all_data.get("ai_generated_data", {})
    step_data = ai_data.get(f"step_{data.step}", {})
    options = step_data.get("options", [])

    if data.option_index < 0 or data.option_index >= len(options):
        raise HTTPException(status_code=400, detail="无效的方案索引")

    selected = options[data.option_index]
    save_step_data(session["id"], data.step, selected)

    _init_logger.info(f"[选择方案] 步骤{data.step} - 用户选择了方案: {selected.get('option_name', '')}")
    return {"success": True, "data": selected}


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
        "core_selling_points": selected_package.get("core_selling_points", ""),
        "opening_hook": selected_package.get("opening_hook", "")
    }
    
    save_step_data(session["id"], 6, {"constraints": constraints_data})
    
    _init_logger.info(f"[选择方案] 步骤6 - 用户选择了方案 {data.package_index}")
    
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


def _load_init_prompt(prompt_name: str) -> Dict[str, str]:
    """从 prompts/{prompt_name}_prompt.md 加载 YAML front matter 格式的 prompt 模板。

    与 base_executor._load_prompt 逻辑一致，支持 system_prompt / user_prompt 字段。
    """
    prompt_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), '..', 'prompts', f'{prompt_name}_prompt.md'
    ))
    if not os.path.exists(prompt_path):
        return {"system_prompt": "", "user_prompt": ""}

    with open(prompt_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    # 去除 YAML front matter 分隔符
    if content.startswith('---'):
        content = content[3:].strip()
    if content.endswith('---'):
        content = content[:-3].strip()

    lines = content.split('\n')
    system_prompt = ''
    user_prompt = ''
    in_user_prompt = False
    in_multiline = False

    for line in lines:
        if line.startswith('system_prompt:'):
            in_user_prompt = False
            in_multiline = False
            value = line.replace('system_prompt:', '').strip()
            if value.startswith('|'):
                in_multiline = True
                system_prompt = ''
            else:
                system_prompt = value
        elif line.startswith('user_prompt:'):
            in_user_prompt = True
            in_multiline = False
            value = line.replace('user_prompt:', '').strip()
            if value.startswith('|'):
                in_multiline = True
                user_prompt = ''
            else:
                user_prompt = value
        elif in_user_prompt and in_multiline:
            user_prompt += line + '\n'
        elif not in_user_prompt and in_multiline:
            system_prompt += line + '\n'

    return {"system_prompt": system_prompt.strip(), "user_prompt": user_prompt.strip()}


def _get_available_genres() -> list:
    """从 genres_json 目录读取系统支持的题材列表。"""
    genres_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'genres_json')
    genres_dir = os.path.abspath(genres_dir)
    genres = []
    if os.path.exists(genres_dir):
        for filename in os.listdir(genres_dir):
            if filename.endswith('.json'):
                genres.append(filename[:-5])
    genres.sort()
    return genres


def _get_project_prompt(current_data: Dict, genre: str) -> tuple:
    tpl = _load_init_prompt('init_project')
    project = current_data.get('project', current_data)
    title = project.get('title', '')
    existing_one_liner = project.get('one_liner', '')
    existing_core_conflict = project.get('core_conflict', '')

    # 获取系统支持的真实题材列表
    available_genres = _get_available_genres()
    genre_list_str = '、'.join(available_genres) if available_genres else '修仙、科幻、都市异能等'
    example_genre = available_genres[0] if available_genres else '修仙'

    user_prompt = tpl['user_prompt'].format(
        title=title,
        genre_display=genre if genre else '未选择',
        one_liner_display=existing_one_liner if existing_one_liner else '未填写',
        core_conflict_display=existing_core_conflict if existing_core_conflict else '未填写',
        genre_list_str=genre_list_str,
        example_genre=example_genre,
    )
    return tpl['system_prompt'], user_prompt


def _get_protagonist_prompt(current_data: Dict, genre: str) -> tuple:
    tpl = _load_init_prompt('init_protagonist')
    project = current_data.get('project', current_data)
    protagonist = current_data.get('protagonist', {})

    def _or_unset(val):
        return val if val else '未填写'

    user_prompt = tpl['user_prompt'].format(
        project_title=project.get('title', ''),
        genre=genre,
        one_liner=project.get('one_liner', ''),
        core_conflict=project.get('core_conflict', ''),
        protagonist_name=_or_unset(protagonist.get('name', '')),
        protagonist_desire=_or_unset(protagonist.get('desire', '')),
        protagonist_flaw=_or_unset(protagonist.get('flaw', '')),
        protagonist_archetype=_or_unset(protagonist.get('archetype', '')),
        protagonist_villain_mirror=_or_unset(protagonist.get('villain_mirror', '')),
    )
    return tpl['system_prompt'], user_prompt


def _get_golden_finger_prompt(current_data: Dict, genre: str) -> tuple:
    tpl = _load_init_prompt('init_golden_finger')
    project = current_data.get('project', current_data)
    protagonist = current_data.get('protagonist', {})
    golden_finger = current_data.get('golden_finger', {})

    def _or_unset(val):
        return val if val else '未填写'

    user_prompt = tpl['user_prompt'].format(
        project_title=project.get('title', ''),
        genre=genre,
        one_liner=project.get('one_liner', ''),
        core_conflict=project.get('core_conflict', ''),
        protagonist_name=protagonist.get('name', ''),
        protagonist_desire=protagonist.get('desire', ''),
        protagonist_flaw=protagonist.get('flaw', ''),
        gf_type=_or_unset(golden_finger.get('type', '')),
        gf_name=_or_unset(golden_finger.get('name', '')),
        gf_style=_or_unset(golden_finger.get('style', '')),
        gf_visibility=_or_unset(golden_finger.get('visibility', '')),
        gf_irreversible_cost=_or_unset(golden_finger.get('irreversible_cost', '')),
    )
    return tpl['system_prompt'], user_prompt


def _get_world_prompt(current_data: Dict, genre: str) -> tuple:
    tpl = _load_init_prompt('init_world')
    project = current_data.get('project', current_data)
    protagonist = current_data.get('protagonist', {})
    golden_finger = current_data.get('golden_finger', {})
    world = current_data.get('world', {})

    def _or_unset(val):
        return val if val else '未填写'

    user_prompt = tpl['user_prompt'].format(
        project_title=project.get('title', ''),
        genre=genre,
        one_liner=project.get('one_liner', ''),
        core_conflict=project.get('core_conflict', ''),
        protagonist_name=protagonist.get('name', ''),
        protagonist_desire=protagonist.get('desire', ''),
        gf_type=golden_finger.get('type', ''),
        gf_name=golden_finger.get('name', ''),
        world_complexity=_or_unset(world.get('worldview_level', '')),
        power_system=_or_unset(world.get('power_system', '')),
        geography=_or_unset(world.get('geography', '')),
        history=_or_unset(world.get('history', '')),
        key_locations=_or_unset(world.get('key_locations', '')),
    )
    return tpl['system_prompt'], user_prompt


def _get_constraints_prompt(current_data: Dict, genre: str) -> tuple:
    tpl = _load_init_prompt('init_constraints')
    project = current_data.get('project', current_data)
    protagonist = current_data.get('protagonist', {})
    golden_finger = current_data.get('golden_finger', {})
    world = current_data.get('world', {})
    constraints = current_data.get('constraints', {})

    def _or_unset(val):
        return val if val else '未填写'

    user_prompt = tpl['user_prompt'].format(
        project_title=project.get('title', ''),
        genre=genre,
        one_liner=project.get('one_liner', ''),
        core_conflict=project.get('core_conflict', ''),
        protagonist_name=protagonist.get('name', ''),
        protagonist_desire=protagonist.get('desire', ''),
        protagonist_flaw=protagonist.get('flaw', ''),
        gf_type=golden_finger.get('type', ''),
        gf_name=golden_finger.get('name', ''),
        world_scale=world.get('scale', '') or world.get('worldview_level', ''),
        power_system_type=world.get('power_system_type', '') or world.get('power_system', ''),
        word_count_chapter=_or_unset(constraints.get('word_count_chapter', '')),
        prologue=_or_unset(constraints.get('prologue', '')),
        first_chapter=_or_unset(constraints.get('first_chapter', '')),
        style=_or_unset(constraints.get('style', '')),
        tropes=_or_unset(constraints.get('tropes', '')),
    )
    return tpl['system_prompt'], user_prompt


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