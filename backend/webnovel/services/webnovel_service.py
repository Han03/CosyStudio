"""网文创作服务。

整合 Webnovel Writer 的核心能力到剧本编辑器：
1. 上下文构建（前文、角色、世界观、名词解释、卷纲规划）
2. RAG语义检索
3. 章节创作（起草、审查、润色）
4. 质量审查（爽点、一致性、节奏、OOC、连贯性、追读力）
5. 事实记录
6. 自动备份
7. 后台任务管理
"""

import re
import os
import json
import time
import asyncio
import hashlib
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

from utils.logger import log_manager
from repositories import (
    get_script, get_script_chapters_all, get_script_chapter, get_script_lines, get_script_characters,
    get_writing_tasks, add_writing_task, update_writing_task, get_writing_task,
    get_ebook, get_chapters
)
from webnovel.repositories import (
    get_webnovel_project_by_script, get_volume_outlines_by_project,
    get_chapter_meta_list, get_chapter_meta, update_chapter_meta,
    add_review_record, get_review_records, get_chapter_review_summary,
    get_worldview_by_project, get_timelines_by_project, add_timeline, add_timeline_chapter,
    get_webnovel_state_by_project, update_webnovel_state, add_webnovel_state,
    add_rag_chunk, update_rag_embedding, search_rag_chunks,
    get_chapter_plans_by_volume
)
from core.model_executor import get_model_executor
from infrastructure.websocket_broadcast import ws_broadcast_manager


class WebnovelService:
    """网文创作服务。"""

    REVIEW_DIMENSIONS = [
        {"key": "excitement", "name": "爽点设计", "description": "是否有足够的爽点，打脸、逆袭、升级是否爽快有力"},
        {"key": "face_slapping", "name": "打脸力度", "description": "打脸情节是否铺垫充分，反击是否爽快解气"},
        {"key": "consistency", "name": "设定一致性", "description": "人物性格、设定、世界观是否保持一致"},
        {"key": "rhythm", "name": "节奏控制", "description": "情节推进是否合理，张弛有度，是否有拖沓"},
        {"key": "ooc", "name": "OOC检查", "description": "人物行为是否符合其设定，是否有OOC行为"},
        {"key": "coherence", "name": "逻辑连贯", "description": "情节是否连贯，逻辑是否通顺"},
        {"key": "retention", "name": "追读力", "description": "是否能吸引读者继续阅读，是否有悬念和钩子"},
        {"key": "dialogue", "name": "对话质量", "description": "对话是否符合人物性格，是否有潜台词，是否生动"},
        {"key": "description", "name": "描写水平", "description": "场景、情感描写是否有画面感，是否调动五感"},
        {"key": "upgrade", "name": "升级感", "description": "实力提升是否有清晰的等级感和成就感"},
    ]

    def __init__(self):
        self._logger = log_manager.get_logger("webnovel_service")
        self._model_executor = get_model_executor()
        self._running_tasks: dict = {}
        self._stop_flags: dict = {}

    async def continue_chapter(self, script_id: int, chapter_index: Optional[int], prompt: str = "", enable_polish: bool = True, auto_apply: bool = False) -> Dict[str, Any]:
        """创作章节。

        完整流程：
        1. 检查是否已有运行中的任务
        2. 自动判断需要创作的章节（如果未指定）
        3. 创建创作任务
        4. 构建上下文
        5. 生成写作任务书
        6. 起草正文（草稿）
        7. 质量审查（审查）
        8. 润色优化（优化）
        9. 记录事实
        10. 更新任务状态
        """
        script = get_script(script_id)
        if script is None:
            return {"success": False, "error": "剧本不存在"}

        # 清理残留的 "running" 任务（服务器意外中断后可能残留）
        running_tasks = get_writing_tasks(script_id, None, "running")
        for rt in (running_tasks or []):
            # 如果任务已有结果（polished或draft），说明已完成但状态未更新，标记为completed
            if rt.get("polished") or rt.get("draft"):
                update_writing_task(rt["id"], status="completed", progress=100,
                                   progress_message="服务重启后自动标记为完成", current_step="完成")
            else:
                update_writing_task(rt["id"], status="failed", error_message="服务中断，任务自动标记为失败")

        if chapter_index is None:
            chapter_index = self._determine_continue_chapter(script_id)

        # 再次检查清理后是否还有 running 任务
        running_tasks = get_writing_tasks(script_id, None, "running")
        if running_tasks:
            return {"success": False, "error": "剧本已有正在运行的创作任务"}

        task = add_writing_task(script_id, chapter_index, "continue", prompt=prompt)
        task_id = task["id"]

        asyncio.create_task(self._execute_writing_workflow(task_id, enable_polish=enable_polish, auto_apply=auto_apply))

        return {
            "success": True,
            "task_id": task_id,
            "chapter_index": chapter_index,
            "status": "running",
            "message": f"创作任务已创建，目标章节: 第{chapter_index}章"
        }

    def _determine_continue_chapter(self, script_id: int) -> int:
        """自动判断创作章节。

        以已有脚本章节为主要依据，webnovel_state仅在没有章节时作为回退。
        """
        chapters = get_script_chapters_all(script_id)
        if not chapters:
            # 没有已有章节，使用 webnovel_state 中的章节号作为回退
            project = get_webnovel_project_by_script(script_id)
            if project:
                state = get_webnovel_state_by_project(project["id"])
                if state:
                    return (state.get("current_chapter", 0) or 0) + 1
            return 1

        max_index = max(ch["chapter_index"] for ch in chapters)

        # 找到最大章节，检查其字数
        for ch in chapters:
            if ch["chapter_index"] == max_index:
                if ch.get("word_count", 0) >= 50:
                    # 最后一章字数足够，创作下一章
                    return max_index + 1
                # 最后一章字数不足，继续创作该章
                return max_index

        return max_index + 1

    async def _broadcast_task_status(self, task_id: int):
        """广播任务状态到WebSocket。"""
        try:
            task = get_writing_task(None, task_id)
            if not task:
                return

            script_id = task["script_id"]
            status = {
                "id": task["id"],
                "script_id": task["script_id"],
                "chapter_index": task["chapter_index"],
                "status": task["status"],
                "progress": task["progress"],
                "progress_message": task["progress_message"],
                "error_message": task["error_message"],
                "current_step": task["current_step"],
                "step_result": task["step_result"],
                "step_name": task.get("step_result", ""),
                "draft": task["draft"],
                "polished": task["polished"],
                "review_result": task["review_result"],
                "facts_recorded": task["facts_recorded"],
                "context": task["context"],
            }
            await ws_broadcast_manager.broadcast_continue_task_update(script_id, task_id, status)
        except Exception as e:
            self._logger.error(f"[WebnovelService] 广播任务状态失败: {e}")

    async def _execute_writing_workflow(self, task_id: int, enable_polish: bool = True, auto_apply: bool = False):
        """执行完整的写作工作流。

        完整流程判断：
        1. 检查是否有待生成的章节规划（written=0）
        2. 如果没有，则先进行规划
        """
        try:
            task = get_writing_task(None, task_id)
            if not task:
                return

            script_id = task["script_id"]
            chapter_index = task["chapter_index"]
            user_prompt = task.get("prompt", "")

            update_writing_task(task_id, status="running", progress=5, progress_message="初始化任务...", 
                               current_step="初始化", step_result="初始化")
            await self._broadcast_task_status(task_id)

            outline_ok = await self._prepare_outline_flow(script_id, task_id)
            if not outline_ok:
                # _prepare_outline_flow 内部已设置 status="failed" 并广播
                self._logger.warning(f"[WebnovelService] 大纲准备失败，任务 {task_id} 终止")
                return

            # 大纲准备完成后检查中断
            if self._stop_flags.get(task_id, False):
                update_writing_task(task_id, status="cancelled", progress=0,
                                   progress_message="创作已中断", current_step="中断", step_result="大纲准备阶段中断")
                await self._broadcast_task_status(task_id)
                return

            update_writing_task(task_id, progress=10, progress_message="大纲准备完成，开始写作流程...",
                               current_step="大纲准备", step_result="大纲准备")
            await self._broadcast_task_status(task_id)

            from webnovel.pipeline.orchestrator import PipelineOrchestrator

            # 传递中断检查回调，使 pipeline 能在步骤间响应取消
            def _stop_check():
                return self._stop_flags.get(task_id, False)

            orchestrator = PipelineOrchestrator(script_id, chapter_index, task_id, stop_check=_stop_check)
            result = await orchestrator.execute_pipeline(enable_polish=enable_polish, user_prompt=user_prompt)

            polished_content = result.get("context", {}).get("polished_content", "")
            # 未开启润色时，用审查后的草稿作为最终内容
            if not polished_content and not enable_polish:
                polished_content = result.get("context", {}).get("revised_draft", "") or result.get("context", {}).get("draft_content", "")
            
            if polished_content and polished_content.strip():
                from webnovel.repositories import get_webnovel_project_by_script
                project = get_webnovel_project_by_script(script_id)

            # 处理中断/完成/失败三种状态
            if result.get("interrupted"):
                status = "cancelled"
                progress = 0
                message = "创作已中断"
            elif result["success"]:
                status = "completed"
                progress = 100
                message = "创作完成"
            else:
                status = "failed"
                progress = 0
                message = f"创作失败，{result['failed_steps']}个步骤出错"

            update_writing_task(
                task_id,
                status=status,
                progress=progress,
                progress_message=message,
                current_step="完成",
                step_result=message,
                draft=result.get("context", {}).get("revised_draft", ""),
                polished=polished_content,
                review_result=json.dumps(result.get("context", {}).get("review_result", [])) if result.get("context", {}).get("review_result") else "",
                facts_recorded=json.dumps(result.get("context", {}).get("facts", [])) if result.get("context", {}).get("facts") else "",
                context=json.dumps(result.get("context", {}))
            )
            await self._broadcast_task_status(task_id)

            if polished_content and polished_content.strip():
                # 不再自动覆盖章节内容，等待用户在模态框中点击"应用结果"
                # 更新 webnovel_state 的当前章节和字数
                await self._update_state_after_chapter(script_id, chapter_index, polished_content)
                # 获取 project_id 用于后续操作
                _project = get_webnovel_project_by_script(script_id)
                _project_id = _project["id"] if _project else 0
                if _project_id:
                    # 提取追读钩子并回写 chapter_meta
                    await self._extract_and_save_hook(_project_id, chapter_index, polished_content)
                    # 追读钩子提取完成后，标记章节元数据为已完成
                    _meta = get_chapter_meta(_project_id, chapter_index)
                    if _meta:
                        update_chapter_meta(_meta["id"], hook_type="已完成")
                    # 存储 RAG 向量片段
                    await self._store_rag_chunk(_project_id, chapter_index, polished_content)

                # 自动应用创作结果
                if auto_apply:
                    self._logger.info(f"[WebnovelService] 自动应用创作结果，task_id={task_id}, chapter_index={chapter_index}")
                    apply_result = await self.apply_continue_result(script_id, chapter_index, task_id)
                    if not apply_result.get("success"):
                        self._logger.error(f"[WebnovelService] 自动应用失败: {apply_result.get('error')}")
                    else:
                        self._logger.info(f"[WebnovelService] 自动应用成功，第{chapter_index}章")
        except Exception as e:
            self._logger.error(f"[WebnovelService] 写作工作流执行失败: {e}")
            # 异常时也检查是否因中断导致
            if self._stop_flags.get(task_id, False):
                update_writing_task(task_id, status="cancelled", progress=0,
                                   progress_message="创作已中断", current_step="中断", step_result=str(e))
            else:
                update_writing_task(task_id, status="failed", error_message=str(e),
                                   progress_message=f"执行失败: {str(e)[:100]}",
                                   current_step="失败", step_result=str(e))
            await self._broadcast_task_status(task_id)

    async def _prepare_outline_flow(self, script_id: int, task_id: int) -> bool:
        """检查当前创作章节是否有章节规划，若无则只生成该章的规划。

        流程：
        1. 根据 task 的 chapter_index 找到对应的卷纲
        2. 检查该章节是否已有 chapter_plan
        3. 若无，只调用 _execute_plan_for_chapter 生成该章的规划
        """
        try:
            task = get_writing_task(None, task_id)
            if not task:
                return False

            chapter_num = task["chapter_index"]
            project = get_webnovel_project_by_script(script_id)
            if not project:
                self._logger.warning(f"[WebnovelService] 项目不存在，script_id={script_id}")
                return False

            project_id = project["id"]
            volume_outlines = get_volume_outlines_by_project(project_id)
            if not volume_outlines:
                self._logger.info(f"[WebnovelService] 无卷纲数据，跳过章节规划检查")
                return True

            # 根据 chapter_num 定位所在卷纲
            target_volume = None
            for vo in volume_outlines:
                if vo["chapter_start"] <= chapter_num <= vo["chapter_end"]:
                    target_volume = vo
                    break

            if not target_volume:
                self._logger.info(
                    f"[WebnovelService] 第{chapter_num}章未匹配到卷纲"
                )
                return False

            volume_number = target_volume["volume_number"]
            vo_id = target_volume["id"]

            # 检查当前创作章节是否已有规划
            existing_plans = get_chapter_plans_by_volume(vo_id)
            has_plan = any(p.get("chapter_index") == chapter_num for p in existing_plans)
            if has_plan:
                self._logger.info(
                    f"[WebnovelService] 第{chapter_num}章已有章节规划，无需重新生成"
                )
                return True

            # 当前章节无规划，只生成该章的规划
            self._logger.info(
                f"[WebnovelService] 第{chapter_num}章无章节规划，开始自动生成..."
            )
            update_writing_task(
                task_id, progress=5,
                progress_message=f"第{chapter_num}章无章节规划，正在自动生成...",
                current_step="章节规划",
                step_result="章节规划"
            )
            await self._broadcast_task_status(task_id)

            plan_result = await self._execute_plan_for_chapter(
                script_id, task_id, target_volume, chapter_num
            )

            if plan_result.get("success"):
                self._logger.info(
                    f"[WebnovelService] 第{chapter_num}章规划自动生成成功"
                )
                return True
            else:
                error_msg = plan_result.get("error_message", "章节规划生成失败")
                self._logger.error(
                    f"[WebnovelService] 第{chapter_num}章规划生成失败: {error_msg}"
                )
                update_writing_task(
                    task_id, status="failed",
                    error_message=error_msg,
                    progress_message=f"章节规划生成失败: {error_msg[:100]}",
                    current_step="失败",
                    step_result=error_msg
                )
                await self._broadcast_task_status(task_id)
                return False

        except Exception as e:
            self._logger.error(f"[WebnovelService] 大纲准备流程异常: {e}")
            update_writing_task(
                task_id, status="failed",
                error_message=str(e),
                progress_message=f"大纲准备失败: {str(e)[:100]}",
                current_step="失败",
                step_result=str(e)
            )
            await self._broadcast_task_status(task_id)
            return False

    async def _execute_plan_for_existing_volume(self, script_id: int, task_id: int, volume_index: int) -> Dict[str, Any]:
        """为已有卷一次性生成全部章节规划。

        当卷纲已存在但 webnovel_chapter_plan 表无数据时调用，
        使用 PlanExecutor 的 regenerate_plans 模式，单次 LLM 调用
        生成整卷的全部章节规划。
        """
        try:
            from webnovel.pipeline.executors.plan_executor import PlanExecutor
            executor = PlanExecutor(script_id, 0, task_id)
            result = await executor.execute({"volume_number": volume_index, "regenerate_plans": True})

            if result.success:
                update_writing_task(task_id, progress=8, progress_message=result.step_summary,
                                   current_step="章节规划", step_result="章节规划")
                await self._broadcast_task_status(task_id)
                return {"success": True, "result": result}
            else:
                return {"success": False, "error_message": result.error_message}
        except Exception as e:
            return {"success": False, "error_message": str(e)}

    async def _execute_plan_for_chapter(
        self, script_id: int, task_id: int, volume_outline: Dict, chapter_num: int
    ) -> Dict[str, Any]:
        """为单个章节生成规划。

        当智能创作时目标章节尚无规划时调用，只生成该章的规划，
        不影响卷内其他章节的已有规划。
        """
        try:
            from webnovel.pipeline.executors.plan_executor import PlanExecutor
            from webnovel.repositories import (
                get_character_cards_by_project, delete_chapter_plans_in_range,
                get_character_group_by_project, get_character_group_members
            )

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return {"success": False, "error_message": "项目不存在"}

            vo_id = volume_outline["id"]
            volume_number = volume_outline.get("volume_number", 1)

            # 只清除该章的旧规划（如果有）
            delete_chapter_plans_in_range(vo_id, chapter_num, chapter_num)

            executor = PlanExecutor(script_id, 0, task_id)
            protagonist_list = get_character_cards_by_project(project["id"], "protagonist")
            protagonist = protagonist_list[0] if protagonist_list else {}

            # 加载角色组数据，确保拆章 prompt 中包含主角团信息
            char_group = get_character_group_by_project(project["id"])
            char_group_members = []
            if char_group:
                char_group_members = get_character_group_members(char_group["id"])

            chapter_plans = await executor._generate_chapter_plans(
                project, volume_outline, protagonist, volume_number,
                start_chapter=chapter_num, end_chapter=chapter_num,
                char_group=char_group, char_group_members=char_group_members
            )

            plan_count = 0
            if chapter_plans:
                plan_count = executor._save_chapter_plans(vo_id, chapter_plans)

            if plan_count > 0:
                summary = f"第{chapter_num}章规划已生成：{plan_count}章"
                update_writing_task(
                    task_id, progress=8, progress_message=summary,
                    current_step="章节规划", step_result="章节规划"
                )
                await self._broadcast_task_status(task_id)
                return {"success": True}
            else:
                return {"success": False, "error_message": "章节规划生成失败：LLM未返回有效数据"}
        except Exception as e:
            return {"success": False, "error_message": str(e)}

    async def _build_context(self, script_id: int, chapter_index: int) -> Dict[str, Any]:
        """构建写作上下文。"""
        context = {}

        # 🔴 注入 script_id / project_id 到 context，供下游 LLM 调用时
        # 传递给 execute_text_chat 统一入口，确保日志记录能关联到脚本/项目
        context["script_id"] = script_id

        project = get_webnovel_project_by_script(script_id)
        if project:
            context["project_id"] = project["id"]
            worldview = get_worldview_by_project(project["id"])
            context["world_settings"] = [worldview] if worldview else []
        else:
            context["project_id"] = 0
            context["world_settings"] = []
        context["characters"] = get_script_characters(script_id)

        project = get_webnovel_project_by_script(script_id)
        if project:
            context["volume_outlines"] = get_volume_outlines_by_project(project["id"])
            # chapter_plans 由 ContextBuilderExecutor 负责填充，此处不再用 chapter_meta 冒充
            context["chapter_plans"] = []
        else:
            context["volume_outlines"] = []
            context["chapter_plans"] = []

        context["previous_chapters"] = []
        for i in range(max(0, chapter_index - 3), chapter_index):
            lines = get_script_lines(script_id, i)
            if lines:
                content = "\n".join(line["content"] for line in lines)
                context["previous_chapters"].append({
                    "chapter_index": i,
                    "content": content[:2000] if len(content) > 2000 else content,
                })

        current_lines = get_script_lines(script_id, chapter_index)
        if current_lines:
            context["current_content"] = "\n".join(line["content"] for line in current_lines)
        else:
            context["current_content"] = ""

        rag_chunks = []
        if context.get("current_content") and project:
            try:
                from core.global_manager import global_manager
                embedding_model = getattr(global_manager, 'qwen_embedding_model', None)
                if embedding_model and embedding_model.is_loaded():
                    embeddings = embedding_model.encode([context["current_content"][:300]])
                    if embeddings and len(embeddings) > 0:
                        rag_chunks = search_rag_chunks(project["id"], embeddings[0].tolist(), limit=5)
            except Exception:
                pass
        context["rag_context"] = [chunk["content"] for chunk in rag_chunks]

        return context

    async def _generate_writing_brief(self, context: Dict[str, Any], user_prompt: str = "") -> str:
        """生成写作任务书。"""
        prompt_parts = [
            "你是一位拥有10年经验的顶级网文编辑，请根据以下上下文生成一份专业的写作任务书：\n",
            "\n【世界观设定】",
        ]
        for setting in context.get("world_settings", []):
            prompt_parts.append(f"- {setting['name']}: {setting['content'][:300]}")

        prompt_parts.append("\n【角色设定】")
        for char in context.get("characters", []):
            personality = char.get("personality", "")
            background = char.get("background", "")
            voice_style = char.get("voice_style", "")
            prompt_parts.append(f"- {char['role']}:")
            if personality:
                prompt_parts.append(f"  * 性格: {personality[:100]}")
            if background:
                prompt_parts.append(f"  * 背景: {background[:100]}")
            if voice_style:
                prompt_parts.append(f"  * 说话风格: {voice_style[:50]}")
            prompt_parts.append(f"  * 标签: {char.get('tags', '')[:50]}")

        prompt_parts.append("\n【前文内容】")
        for prev in context.get("previous_chapters", []):
            prompt_parts.append(f"第{prev['chapter_index']}章:\n{prev['content']}")

        if context.get("chapter_plans"):
            prompt_parts.append("\n【章节规划】")
            for plan in context["chapter_plans"]:
                prompt_parts.append(f"- 标题: {plan['chapter_title']}")
                prompt_parts.append(f"- 概要: {plan['summary']}")
                prompt_parts.append(f"- 关键事件: {plan['key_events']}")
                prompt_parts.append(f"- 预期爽点: {plan.get('expected_cool_points', '')}")

        prompt_parts.append(f"\n【当前内容】\n{context.get('current_content', '')}")

        if user_prompt:
            prompt_parts.append(f"\n【用户要求】\n{user_prompt}")

        prompt_parts.append("\n\n请生成一份详细的写作任务书，包括：")
        prompt_parts.append("1. 本章目标：明确本章要达成的叙事目标")
        prompt_parts.append("2. 情节推进：详细列出需要发生的事件及顺序")
        prompt_parts.append("3. 人物关系：需要展现或发展的人物关系")
        prompt_parts.append("4. 风格要求：语言风格、情感基调、节奏控制")
        prompt_parts.append("5. 爽点设计：本章需要设计的爽点（打脸、逆袭、升级等）")
        prompt_parts.append("6. 字数要求：建议字数（3000-5000字）")
        prompt_parts.append("7. 禁忌事项：需要避免的情节或描写")

        full_prompt = "\n".join(prompt_parts)

        # 🔴 提取 script_id / project_id 传递给统一日志入口
        _sid = int(context.get("script_id", 0) or 0)
        _pid = int(context.get("project_id", 0) or 0)

        result = await self._model_executor.execute_text_chat(
            prompt=full_prompt,
            system_prompt="你是一位拥有10年经验的顶级网文编辑，精通各种题材的小说创作，擅长设计爽点和控制节奏",
            max_tokens=1500,
            script_id=_sid,
            project_id=_pid,
            executor_name="webnovel_service",
            prompt_name="generate_writing_brief",
        )
        content = result.get("content", "") if result else ""
        return content if content.strip() else ""

    async def _generate_draft(self, writing_brief: str, script_id: int = 0, project_id: int = 0) -> str:
        """根据写作任务书起草正文。"""
        prompt = f"""你是一位畅销网文作家，拥有多部百万字完本作品，请根据以下写作任务书创作章节内容：

【写作任务书】
{writing_brief}

【写作要求】
1. 开篇要有吸引力，迅速抓住读者注意力（黄金三章法则）
2. 每500字左右设置一个小高潮或悬念，保持阅读节奏
3. 对话要符合人物性格，有潜台词，避免直白叙述
4. 场景描写要有画面感，调动读者的五感
5. 适当使用短句和感叹号增强节奏感
6. 结尾要有钩子，引导读者追读下一章
7. 字数控制在3000-5000字

【网文技巧】
- 打脸情节：铺垫要充分，反击要爽快
- 升级体系：明确等级差距，展示实力提升
- 情感描写：细腻真实，引发共鸣
- 节奏控制：张弛有度，快慢结合

请直接输出正文内容，不要包含标题和额外说明。
"""

        result = await self._model_executor.execute_text_chat(
            prompt=prompt,
            system_prompt="你是一位畅销网文作家，擅长设计爽点、控制节奏，语言风格生动有力，情节紧凑吸引人",
            max_tokens=5000,
            script_id=int(script_id or 0),
            project_id=int(project_id or 0),
            executor_name="webnovel_service",
            prompt_name="generate_draft",
        )
        content = result.get("content", "") if result else ""
        return content if content.strip() else ""

    async def _review_chapter(self, draft: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """多维度审查章节质量（单次LLM调用完成所有维度）。"""
        _sid = int(context.get("script_id", 0) or 0)
        _pid = int(context.get("project_id", 0) or 0)

        # 构建维度说明列表
        dimension_lines = []
        for d in self.REVIEW_DIMENSIONS:
            dimension_lines.append(f"- {d['name']}({d['key']})：{d['description']}")
        dimensions_text = "\n".join(dimension_lines)

        prompt = f"""请作为专业网文编辑，从以下所有维度一次性审查该章节内容：

【审查维度】
{dimensions_text}

【上下文】
世界观设定: {json.dumps([s['name'] for s in context.get('world_settings', [])], ensure_ascii=False)}
角色列表: {json.dumps([c['role'] for c in context.get('characters', [])], ensure_ascii=False)}
前文内容: {context.get('previous_content', '')[:500]}

【章节内容】
{draft[:4000]}

【审查要求】
请对每个维度分别评分，按照以下格式输出JSON：
{{
    "reviews": [
        {{
            "dimension": "维度key（如excitement/consistency等）",
            "name": "维度中文名",
            "score": 1-10的整数评分,
            "issues": [
                {{
                    "severity": "critical/high/medium/low",
                    "location": "问题位置描述，如第3段/第100字",
                    "description": "问题详细描述",
                    "evidence": "原文引用或上下文对比",
                    "fix_hint": "修复建议"
                }}
            ],
            "strengths": ["优点1", "优点2"],
            "suggestions": "综合修改建议"
        }}
    ]
}}

注意：
- reviews数组必须包含上述所有维度，每个维度一条
- severity=critical 表示严重问题，需要强制修改
- severity=high 表示重要问题，建议修改
- severity=medium/low 表示一般问题，可选择性修改
- issues数组可以为空（如果没有问题）
- 直接输出JSON，不要包含其他内容
"""

        result = await self._model_executor.execute_text_chat(
            prompt=prompt,
            system_prompt="你是一位专业的网文编辑，擅长从多维度进行质量审查，输出严格的JSON格式",
            max_tokens=3000,
            script_id=_sid,
            project_id=_pid,
            executor_name="webnovel_service",
            prompt_name="review_all_dimensions",
        )

        content = result.get("content", "") if result else ""
        results = []

        try:
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'\s*```', '', content)

            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                review_data = json.loads(json_match.group())
            else:
                review_data = {"reviews": []}
        except:
            review_data = {"reviews": []}

        reviews = review_data.get("reviews", [])

        # 将LLM返回的reviews映射到标准格式，确保所有维度都有结果
        reviewed_keys = set()
        for review in reviews:
            dim_key = review.get("dimension", "")
            dim_name = review.get("name", "")
            score = review.get("score", 5)
            issues = review.get("issues", [])
            strengths = review.get("strengths", [])
            suggestions = review.get("suggestions", "")

            feedback_items = []
            for i in issues:
                if isinstance(i, dict) and 'severity' in i and 'description' in i:
                    feedback_items.append(f"{i['severity']}: {i['description']}")
                elif isinstance(i, str):
                    feedback_items.append(i)

            # 匹配到REVIEW_DIMENSIONS中的维度
            matched_dim = None
            for d in self.REVIEW_DIMENSIONS:
                if d["key"] == dim_key or d["name"] == dim_name:
                    matched_dim = d
                    break

            if matched_dim:
                reviewed_keys.add(matched_dim["key"])
                results.append({
                    "dimension": matched_dim["key"],
                    "name": matched_dim["name"],
                    "score": score,
                    "issues": issues,
                    "strengths": strengths,
                    "suggestions": suggestions,
                    "feedback": ", ".join(feedback_items) if feedback_items else "",
                })

        # 补全未被LLM返回的维度，赋予默认中等分数
        for d in self.REVIEW_DIMENSIONS:
            if d["key"] not in reviewed_keys:
                results.append({
                    "dimension": d["key"],
                    "name": d["name"],
                    "score": 5,
                    "issues": [],
                    "strengths": [],
                    "suggestions": "",
                    "feedback": "",
                })

        return results

    async def _polish_chapter(self, draft: str, review_result: List[Dict[str, Any]], script_id: int = 0, project_id: int = 0) -> str:
        """根据审查结果润色章节。"""
        issues = []
        suggestions = []
        blocking_issues = []
        scores = {}
        
        for review in review_result:
            scores[review["dimension"]] = review["score"]
            
            for issue in review.get("issues", []):
                if isinstance(issue, dict) and 'severity' in issue and 'description' in issue:
                    severity = issue.get('severity', '')
                    description = issue.get('description', '')
                    location = issue.get('location', '')
                    fix_hint = issue.get('fix_hint', '')
                    
                    if severity == "critical":
                        blocking_issues.append(f"【严重问题】{location}: {description}\n修复建议: {fix_hint}")
                    elif severity in ["high", "medium"]:
                        issues.append(f"- [{review['name']}] {location}: {description}")
            
            if review.get("suggestions"):
                suggestions.append(f"- [{review['name']}] {review['suggestions']}")

        issues_text = "\n".join(blocking_issues + issues)
        suggestions_text = "\n".join(suggestions)
        
        blocking_text = "【严重问题（必须修改）】\n" + "\n".join(blocking_issues) + "\n\n" if blocking_issues else ""
        
        prompt = f"""你是一位资深网文润色师，请根据以下审查意见和评分全面润色章节内容：

【审查评分】
{json.dumps(scores, ensure_ascii=False, indent=2)}

{blocking_text}【待修改问题】
{issues_text}

【修改建议】
{suggestions_text}

【网文润色技巧】
1. 爽点增强：增加对比、强化反差、延长快感
2. 节奏优化：短句加速、长句减速、适当换行
3. 对话升级：增加潜台词、动作配合、情感递进
4. 描写提升：五感并用、比喻新颖、画面感强
5. 钩子设计：结尾悬念、问题留待、期待感强

【润色要求】
- 保持原有情节和角色不变
- 提升语言感染力和阅读快感
- 增加细节描写，增强代入感
- 优化段落结构，提升节奏感
- 即使没有问题也要主动优化文风

【原始内容】
{draft}

请输出修改后的完整章节内容。
"""

        result = await self._model_executor.execute_text_chat(
            prompt=prompt,
            system_prompt="你是一位资深网文润色师，精通各种题材的小说润色，擅长提升文章的爽点、节奏和感染力",
            max_tokens=5000,
            script_id=int(script_id or 0),
            project_id=int(project_id or 0),
            executor_name="webnovel_service",
            prompt_name="polish_chapter",
        )
        content = result.get("content", "") if result else ""
        return content if content.strip() else draft

    async def _record_facts(self, content: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从章节内容中提取事实并记录。"""
        prompt = f"""请从以下章节内容中提取关键事实：

【章节内容】
{content[:2000]}

【已知设定】
世界观: {json.dumps([s['name'] for s in context.get('world_settings', [])], ensure_ascii=False)}
角色: {json.dumps([c['role'] for c in context.get('characters', [])], ensure_ascii=False)}

请提取以下类型的事实：
1. 新角色出场
2. 角色关系变化
3. 重要事件
4. 伏笔设置
5. 世界观补充

格式：
- 类型: 内容
"""

        # 🔴 提取 script_id / project_id 传递给统一日志入口
        _sid = int(context.get("script_id", 0) or 0)
        _pid = int(context.get("project_id", 0) or 0)

        result = await self._model_executor.execute_text_chat(
            prompt=prompt,
            system_prompt="你是一位专业的内容分析助手，擅长提取文本中的关键信息",
            max_tokens=500,
            script_id=_sid,
            project_id=_pid,
            executor_name="webnovel_service",
            prompt_name="record_facts",
        )

        content = result.get("content", "") if result else ""
        facts = []
        for line in content.split("\n"):
            if line.strip().startswith("- "):
                parts = line[2:].split(":", 1)
                if len(parts) == 2:
                    facts.append({"type": parts[0].strip(), "content": parts[1].strip()})

        return facts

    # ── 内容过滤与标题提取工具 ──────────────────────────────

    @staticmethod
    def _filter_chapter_content(content: str) -> str:
        """过滤章节内容，去除章节标题行和尾部非正文内容。

        过滤规则：
        - 开头 1~3 行内匹配章节标题模式则去除
          支持格式：第N章 标题、第N章：标题、第N章:标题、第N章标题
        - 尾部"（未完待续……）"等尾缀去除
        """
        if not content:
            return content

        lines = content.split('\n')
        filtered_lines = []
        title_skipped = False

        # 章节标题正则：第N章 后可跟冒号/空格/直接跟标题/整行就是第N章
        chapter_title_re = re.compile(
            r'^第[一二三四五六七八九十百千万零\d]+章'
            r'(?:\s*[：:．\s]|(?=[^\d一二三四五六七八九十])|$)',
            re.IGNORECASE,
        )
        chapter_title_en_re = re.compile(r'^Chapter\s+\d+', re.IGNORECASE)

        for i, line in enumerate(lines):
            stripped = line.strip()
            # 仅在前 3 行中检测章节标题
            if not title_skipped and i < 3 and stripped:
                if chapter_title_re.match(stripped) or chapter_title_en_re.match(stripped):
                    title_skipped = True
                    continue
            filtered_lines.append(line)

        result = '\n'.join(filtered_lines).strip()

        # 去除尾部非正文尾缀
        trailing_patterns = [
            r'[\s]*[\(（]未完待续[…….\s]*[\)）][\s]*',
            r'[\s]*[\(（]本章完[\)）][\s]*',
            r'[\s]*[\(（]To be continued[.\s]*[\)）][\s]*',
        ]
        for pattern in trailing_patterns:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

        return result.strip()

    def _extract_chapter_title(self, content: str, script_id: int, chapter_index: int) -> str:
        """获取章节标题。

        优先使用章节规划中的标题，提取失败时再从内容首行尝试，最后回退到占位标题。
        """
        default_title = f"第{chapter_index}章"

        # 1. 优先从章节规划获取标题
        try:
            project = get_webnovel_project_by_script(script_id)
            if project:
                from webnovel.repositories import get_all_chapter_plans_for_project
                volumes = get_all_chapter_plans_for_project(project["id"])
                for vol in volumes:
                    for plan in vol.get("chapter_plans", []):
                        if plan.get("chapter_index") == chapter_index:
                            plan_title = (plan.get("chapter_title") or "").strip()
                            if plan_title:
                                return f"第{chapter_index}章 {plan_title}"
        except Exception:
            pass

        # 2. 从内容首行提取标题（备选）
        if content:
            title_extract_re = re.compile(
                r'^第[一二三四五六七八九十百千万零\d]+章\s*[：:．\s]?\s*(.+)$'
            )
            for line in content.split('\n')[:3]:
                stripped = line.strip()
                if not stripped:
                    continue
                m = title_extract_re.match(stripped)
                if m:
                    extracted = m.group(1).strip()
                    if extracted:
                        return f"第{chapter_index}章 {extracted}"

        return default_title

    # ── 保存创作结果 ──────────────────────────────────────

    async def _save_continue_result(self, script_id: int, chapter_index: int, content: str):
        """保存创作结果到章节（内部使用，不过滤内容）。

        统一使用 add_chapter(chapter_index=...) 确保内容保存到目标索引，
        避免 max_idx+1 与实际 chapter_index 不一致。
        """
        from services.script_service import ScriptService

        try:
            script_service = ScriptService()
            title = f"第{chapter_index}章"
            # add_chapter 内部已处理：目标索引有章节则覆写，无则创建
            script_service.add_chapter(script_id, title, content, chapter_index=chapter_index)

            self._logger.info(f"[WebnovelService] 创作结果已保存到第{chapter_index}章")
        except Exception as e:
            self._logger.error(f"[WebnovelService] 保存创作结果失败: {e}")

    async def apply_continue_result(self, script_id: int, chapter_index: int, task_id: int) -> Dict[str, Any]:
        """应用创作结果到章节（对外接口）。

        完整流程：
        1. 获取任务的创作内容
        2. 过滤章节标题行和尾部非正文内容
        3. 提取实际章节标题
        4. 保存内容到章节（不存在则创建）
        5. 回写章节标题
        6. 通过 WebSocket 通知前端刷新
        """
        from services.script_service import ScriptService

        task = get_writing_task(script_id, task_id)
        if not task:
            return {"success": False, "error": "任务不存在"}

        # 始终使用任务自身记录的 chapter_index，避免前端状态不同步导致写错章节
        task_chapter_index = task.get("chapter_index", chapter_index)
        if task_chapter_index != chapter_index:
            self._logger.warning(
                f"[WebnovelService] 前端传入的 chapter_index={chapter_index} "
                f"与任务的 chapter_index={task_chapter_index} 不一致，以任务为准"
            )
        chapter_index = task_chapter_index

        raw_content = task.get("polished") or task.get("draft") or ""
        if not raw_content.strip():
            return {"success": False, "error": "创作结果为空"}

        # 过滤非正文内容
        filtered_content = self._filter_chapter_content(raw_content)

        # 提取实际章节标题
        actual_title = self._extract_chapter_title(raw_content, script_id, chapter_index)

        try:
            script_service = ScriptService()
            # add_chapter: 目标索引有章节则覆写内容，无则创建
            script_service.add_chapter(
                script_id, actual_title, filtered_content, chapter_index=chapter_index,
            )
            # 回写章节标题（add_chapter 覆写时不会更新 title，需单独调用）
            script_service.update_chapter_title(script_id, chapter_index, actual_title)

            self._logger.info(
                f"[WebnovelService] 创作结果已应用到第{chapter_index}章，标题: {actual_title}"
            )

            # 通过 WebSocket 通知前端
            await ws_broadcast_manager.broadcast_chapter_applied(
                script_id, chapter_index, actual_title, filtered_content,
            )

            return {
                "success": True,
                "chapter_index": chapter_index,
                "title": actual_title,
                "content": filtered_content,
                "word_count": len(filtered_content),
            }
        except Exception as e:
            self._logger.error(f"[WebnovelService] 应用创作结果失败: {e}")
            return {"success": False, "error": str(e)}

    async def _update_state_after_chapter(self, script_id: int, chapter_index: int, content: str):
        """创作完成后更新 webnovel_state 的当前章节和字数。

        如果 state 不存在则自动创建，确保后续 _determine_continue_chapter
        的回退路径可用。
        """
        try:
            project = get_webnovel_project_by_script(script_id)
            if not project:
                return
            state = get_webnovel_state_by_project(project["id"])
            word_count = len(content)

            if not state:
                # state 不存在 → 自动创建
                new_state = add_webnovel_state(
                    project_id=project["id"],
                    current_chapter=chapter_index,
                    total_words=word_count,
                )
                self._logger.info(
                    f"[WebnovelService] 已创建 webnovel_state: current_chapter={chapter_index}, "
                    f"total_words={word_count}"
                )
                return

            # current_chapter 记录已写到的最大章节号
            new_current = max(state.get("current_chapter", 0) or 0, chapter_index)
            new_total_words = (state.get("total_words", 0) or 0) + word_count

            update_webnovel_state(
                state["id"],
                current_chapter=new_current,
                total_words=new_total_words
            )
            self._logger.info(
                f"[WebnovelService] 已更新 webnovel_state: current_chapter={new_current}, "
                f"total_words={new_total_words}"
            )
        except Exception as e:
            self._logger.error(f"[WebnovelService] 更新 webnovel_state 失败: {e}")

    async def _extract_and_save_hook(self, project_id: int, chapter_index: int, content: str):
        """从润色内容中提取追读钩子并回写到 chapter_meta。

        注意：不回写 hook_type，该字段由调用方用于标记状态（如"已完成"）。
        """
        try:
            chapter_meta = get_chapter_meta(project_id, chapter_index)
            if not chapter_meta:
                return

            prompt = f"""请从以下章节内容末尾提取追读钩子（悬念、未解问题、吸引读者继续阅读的悬念点）：

【章节内容末尾】
{content[-800:]}

请输出严格的JSON格式：
{{"hook_content": "钩子内容描述", "hook_type": "悬念式/冲突式/反转型/情感式", "hook_strength": "强/中/弱", "hook_pattern": "钩子手法（如：悬念留白/矛盾激化/信息差/反转）", "ending_emotion": "期待/紧张/感动/愤怒", "ending_time": "场景时间（如：白天/夜晚/黄昏/清晨）", "ending_location": "场景地点"}}
如果没有明显的钩子，hook_content输出空字符串。
"""
            result = await self._model_executor.execute_text_chat(
                prompt=prompt,
                system_prompt="你是一位专业的网文编辑，擅长识别和设计追读钩子。请输出严格的JSON格式。",
                max_tokens=300,
                script_id=0,
                project_id=project_id,
                executor_name="webnovel_service",
                prompt_name="extract_hook",
            )
            response = result.get("content", "") if result else ""

            from utils.llm_json_parser import parse_llm_json
            hook_data = parse_llm_json(
                response,
                executor_name="webnovel_service",
                prompt_name="extract_hook",
            )
            if hook_data and hook_data.get("hook_content"):
                update_chapter_meta(
                    chapter_meta["id"],
                    hook_content=hook_data.get("hook_content", ""),
                    hook_strength=hook_data.get("hook_strength", "中"),
                    hook_pattern=hook_data.get("hook_pattern", ""),
                    ending_emotion=hook_data.get("ending_emotion", ""),
                    ending_time=hook_data.get("ending_time", ""),
                    ending_location=hook_data.get("ending_location", ""),
                )
                self._logger.info(f"[WebnovelService] 已提取并保存第{chapter_index}章追读钩子")
        except Exception as e:
            self._logger.error(f"[WebnovelService] 提取追读钩子失败: {e}")

    async def _store_rag_chunk(self, project_id: int, chapter_index: int, content: str):
        """将章节摘要存储为 RAG 片段并计算 embedding。"""
        try:
            # 提取章节摘要作为 RAG 片段
            summary = content[:500]
            chunk = add_rag_chunk(
                project_id=project_id,
                content=summary,
                chunk_type="chapter",
                chapter_number=chapter_index,
                metadata=json.dumps({"chapter_index": chapter_index, "word_count": len(content)})
            )

            # 计算 embedding
            from core.global_manager import global_manager
            embedding_model = getattr(global_manager, 'qwen_embedding_model', None)
            if embedding_model and embedding_model.is_loaded():
                embeddings = embedding_model.encode([summary])
                if embeddings and len(embeddings) > 0:
                    update_rag_embedding(chunk["id"], embeddings[0].tolist())
        except Exception as e:
            self._logger.error(f"[WebnovelService] 存储 RAG 片段失败: {e}")

    async def get_task_status(self, script_id: int, task_id: int) -> Optional[Dict[str, Any]]:
        """获取写作任务状态。"""
        task = get_writing_task(script_id, task_id)
        if task:
            return {
                "id": task["id"],
                "script_id": task["script_id"],
                "chapter_index": task["chapter_index"],
                "status": task["status"],
                "progress": task["progress"],
                "progress_message": task["progress_message"],
                "error_message": task["error_message"],
                "created_at": task["created_at"],
                "updated_at": task["updated_at"],
                "draft": task["draft"],
                "polished": task["polished"],
                "review_result": task["review_result"],
                "facts_recorded": task["facts_recorded"],
                "context": task["context"],
            }
        return None

    async def cancel_task(self, script_id: int, task_id: int) -> Dict[str, Any]:
        """取消写作任务。"""
        task = get_writing_task(script_id, task_id)
        if not task:
            return {"success": False, "error": "任务不存在"}

        if task["status"] == "completed":
            return {"success": False, "error": "任务已完成"}

        self._stop_flags[task_id] = True
        update_writing_task(task_id, status="cancelled")

        return {"success": True, "message": "任务已取消"}

    async def get_chapter_review(self, script_id: int, chapter_index: int) -> Dict[str, Any]:
        """获取章节审查结果。"""
        project = get_webnovel_project_by_script(script_id)
        if not project:
            return {
                "chapter_index": chapter_index,
                "dimension_results": [],
                "records": [],
            }
        
        records = get_review_records(project["id"], chapter_index)
        summary = get_chapter_review_summary(project["id"], chapter_index)

        dimension_results = []
        for dimension in self.REVIEW_DIMENSIONS:
            key = dimension["key"]
            avg_score = summary.get(key, {}).get("avg_score", 0)
            count = summary.get(key, {}).get("count", 0)
            dimension_results.append({
                "key": key,
                "name": dimension["name"],
                "avg_score": avg_score,
                "count": count,
            })

        return {
            "chapter_index": chapter_index,
            "dimension_results": dimension_results,
            "records": records,
        }

    async def manual_review(self, script_id: int, chapter_index: int, content: str) -> Dict[str, Any]:
        """手动触发章节审查。"""
        context = await self._build_context(script_id, chapter_index)
        review_result = await self._review_chapter(content, context)

        project = get_webnovel_project_by_script(script_id)
        if project:
            for review in review_result:
                add_review_record(
                    project_id=project["id"],
                    chapter_number=chapter_index,
                    review_type=review["dimension"],
                    score=review["score"],
                    feedback=review["feedback"],
                    suggestions=review["suggestions"]
                )

        return {
            "success": True,
            "chapter_index": chapter_index,
            "review_result": review_result,
        }


_webnovel_service = None


def get_webnovel_service() -> WebnovelService:
    """获取网文创作服务实例。"""
    global _webnovel_service
    if _webnovel_service is None:
        _webnovel_service = WebnovelService()
    return _webnovel_service
