"""网文创作服务。

整合 Webnovel Writer 的核心能力到剧本编辑器：
1. 上下文构建（前文、角色、世界观、名词解释、卷纲规划）
2. RAG语义检索
3. 章节创作（起草、审查、润色）
4. 质量审查（爽点、一致性、节奏、OOC、连贯性、结尾自然度）
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
    get_script, get_script_chapters_all, get_script_chapter,
    get_writing_tasks, add_writing_task, update_writing_task, get_writing_task,
    delete_writing_task, get_active_writing_tasks,
    get_ebook, get_chapters,
    delete_pipeline_logs_by_chapter,
)
from webnovel.repositories import (
    get_webnovel_project, get_webnovel_project_by_script, get_volume_outlines_by_project,
    add_review_record, get_review_records, delete_chapter_review_records,
    get_worldview_by_project,
    get_webnovel_state_by_project, update_webnovel_state, add_webnovel_state,
    get_chapter_plans_by_volume,
    get_character_cards_by_project, get_golden_finger_by_project,
    get_power_system_by_project, get_villains_by_project,
    get_character_card, get_character_items_by_project,
    get_timelines_by_project, delete_timeline_chapters_by_chapter,
    delete_timeline_countdowns_by_planted_chapter, restore_timeline_countdowns_by_trigger_chapter,
    delete_cool_points_by_chapter, delete_character_states_by_chapter,
    delete_worldview_settings_by_chapter, delete_relationships_by_chapter,
    delete_growths_by_chapter, delete_open_loops_by_planted_chapter,
    restore_open_loops_by_resolved_chapter, get_setting_changes_by_chapter,
    delete_setting_changes_by_chapter, delete_character_card,
    update_character_card, get_character_items, mark_character_item_lost,
    delete_items_acquired_in_chapter, restore_items_lost_in_chapter,
    delete_chapter_meta, delete_chapter_plot,
)
from core.model_executor import get_model_executor
from infrastructure.websocket_broadcast import ws_broadcast_manager

# apply 任务超时时间（秒）
_APPLY_TASK_TIMEOUT = 600


class WebnovelService:
    """网文创作服务。"""

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
        9. 更新任务状态

        注：事实记录和伏笔爽点提取已移至“应用创作结果”任务中执行。
        """
        script = get_script(script_id)
        if script is None:
            return {"success": False, "error": "剧本不存在"}

        # 清理残留的进行中任务（服务器意外中断后可能残留）。
        # 含 pending：任务创建后、工作流置 running 前的极短窗口中断会残留，
        # 若不清理会永久阻塞全局互斥检查。
        stale_tasks = (get_writing_tasks(script_id, None, "running") or []) + \
                      (get_writing_tasks(script_id, None, "pending") or [])
        for rt in stale_tasks:
            # apply 类型任务单独处理：检查目标章节是否已有内容
            if rt.get("task_type") == "apply":
                ch = get_script_chapter(script_id, rt.get("chapter_index", 0))
                if ch and (ch.get("word_count") or 0) > 0:
                    update_writing_task(rt["id"], status="completed", progress=100,
                                       progress_message="服务重启后自动标记为完成（章节内容已保存）",
                                       current_step="完成")
                else:
                    update_writing_task(rt["id"], status="failed",
                                       error_message="服务中断，应用任务失败")
                continue
            # 如果任务已有结果（polished或draft），说明已完成但状态未更新，标记为completed
            if rt.get("polished") or rt.get("draft"):
                update_writing_task(rt["id"], status="completed", progress=100,
                                   progress_message="服务重启后自动标记为完成", current_step="完成")
            else:
                update_writing_task(rt["id"], status="failed", error_message="服务中断，任务自动标记为失败")

        if chapter_index is None:
            chapter_index = self._determine_continue_chapter(script_id)

        # 检查剧本级别是否有拆章任务（split）或续写任务（continue），有则拒绝
        active_tasks = (get_writing_tasks(script_id, None, "pending") or []) + \
                       (get_writing_tasks(script_id, None, "running") or [])
        blocking_tasks = [t for t in active_tasks if t.get("task_type") in ("split", "continue")]
        if blocking_tasks:
            return {"success": False, "error": "当前剧本已有创作任务正在进行，请等待完成后再试"}

        # 🔴 本地模型模式下全局只允许一个创作任务：本地 LLM/Embedding/Reranker 为单实例，
        # 推理层虽已串行锁保护，但多任务排队会导致后续任务长时间无响应，入口处直接拒绝更友好。
        # 云端模式下各任务独立请求，不受此限制。
        # 注：统计 pending+running，pending 窗口（创建后到工作流置 running 前）同样互斥。
        if self._is_local_text_predict_default():
            global_active = [t for t in get_active_writing_tasks() if t.get("script_id") != script_id]
            if global_active:
                return {"success": False, "error": "本地模型模式下同一时间仅支持一个创作任务，请等待当前任务完成"}

        task = add_writing_task(script_id, chapter_index, "continue", prompt=prompt)
        task_id = task["id"]

        # 🔴 插入后复检：消除"先查后插"竞态（同一剧本双击/两个编辑器并发请求时，
        # 两个请求可能都通过上方检查）。下方均为同步调用，其间无 await，不会被其他协程交错。
        # 检查剧本级别是否有重复的创作任务
        all_active = (get_writing_tasks(script_id, None, "pending") or []) + \
                     (get_writing_tasks(script_id, None, "running") or [])
        dup_tasks = [t for t in all_active if t.get("task_type") in ("split", "continue")]
        if len(dup_tasks) > 1:
            delete_writing_task(task_id)
            return {"success": False, "error": "当前剧本已有创作任务正在进行，请等待完成后再试"}

        asyncio.create_task(self._execute_writing_workflow(task_id, enable_polish=enable_polish, auto_apply=auto_apply))

        return {
            "success": True,
            "task_id": task_id,
            "chapter_index": chapter_index,
            "status": "running",
            "message": f"创作任务已创建，目标章节: 第{chapter_index}章"
        }

    def _is_local_text_predict_default(self) -> bool:
        """判断当前默认（最高优先级）文本预测能力是否为本地模型。

        无法判断时保守返回 True（按本地处理，宁可拒绝也不并发压模型）。
        """
        try:
            from models.model_capability_manager import capability_manager
            cap = capability_manager.get_best_capability("text_predict")
            if not cap:
                return True
            return cap.get("platform_code", "local") == "local"
        except Exception:
            return True

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

            # 审查结果落库审查记录表，供质量审查报告模态框读取；先清旧数据避免章节重写残留
            review_records = result.get("context", {}).get("review_result", [])
            if review_records and not result.get("interrupted") and chapter_index is not None:
                _rv_project = get_webnovel_project_by_script(script_id)
                if _rv_project:
                    delete_chapter_review_records(_rv_project["id"], chapter_index)
                    for review in review_records:
                        if not isinstance(review, dict):
                            continue
                        add_review_record(
                            project_id=_rv_project["id"],
                            chapter_number=chapter_index,
                            review_type=review.get("dimension", ""),
                            score=int(review.get("score", 0) or 0),
                            feedback=json.dumps({
                                "name": review.get("name", ""),
                                "issues": review.get("issues", []),
                                "strengths": review.get("strengths", []),
                            }, ensure_ascii=False),
                            suggestions=review.get("suggestions", "") or "",
                        )

            await self._broadcast_task_status(task_id)

            if polished_content and polished_content.strip():
                # 事实记录和伏笔爽点提取已移至“应用创作结果”任务中执行
                # 仅更新 webnovel_state 的当前章节和字数
                await self._update_state_after_chapter(script_id, chapter_index, polished_content)
            
                # 自动应用创作结果：创作完成后自动发起 apply 任务
                if auto_apply:
                    self._logger.info(f"[WebnovelService] 自动应用创作结果，task_id={task_id}, chapter_index={chapter_index}")
                    apply_result = await self.apply_continue_result_as_task(script_id, chapter_index, task_id)
                    if not apply_result.get("success"):
                        self._logger.error(f"[WebnovelService] 自动应用失败: {apply_result.get('error')}")
                    else:
                        self._logger.info(f"[WebnovelService] 自动应用任务已创建，apply_task_id={apply_result.get('apply_task_id')}")
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
                            # 防御性清除标题中可能残留的 "第X章" 前缀，避免拼接后出现两个章节号
                            if plan_title:
                                plan_title = re.sub(
                                    r'^第\s*[一二三四五六七八九十百千万零〇两\d]+\s*[章回节]\s*[：:．\s]?\s*',
                                    '', plan_title
                                ).strip()
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

    # ── 应用创作结果任务 ──────────────────────────────────────

    async def apply_continue_result_as_task(self, script_id: int, chapter_index: int, source_task_id: int) -> Dict[str, Any]:
        """将应用创作结果作为异步任务执行。

        Args:
            script_id: 剧本ID
            chapter_index: 目标章节索引
            source_task_id: 创作任务ID（包含 polished/draft 内容的任务）

        Returns:
            {success, apply_task_id, chapter_index} 或 {success: False, error}
        """
        # 互斥检查：该剧本是否已有 apply 类型的 running/pending 任务
        active_tasks = (get_writing_tasks(script_id, None, "running") or []) + \
                       (get_writing_tasks(script_id, None, "pending") or [])
        for t in active_tasks:
            if t.get("task_type") == "apply":
                return {"success": False, "error": "已有应用任务正在进行中"}

        # 创建 apply 类型的 writing_task
        task = add_writing_task(script_id, chapter_index, "apply",
                                prompt=f"应用任务{source_task_id}的创作结果")
        apply_task_id = task["id"]

        # 异步执行应用工作流
        asyncio.create_task(
            self._execute_apply_workflow(apply_task_id, script_id, chapter_index, source_task_id)
        )

        return {
            "success": True,
            "apply_task_id": apply_task_id,
            "chapter_index": chapter_index,
        }

    async def _execute_apply_workflow(self, apply_task_id: int, script_id: int,
                                       chapter_index: int, source_task_id: int):
        """执行应用创作结果的异步工作流。

        流程：
        1. 获取源任务的创作内容
        2. 过滤内容、提取标题
        3. 创建/覆写章节
        4. 执行事实记录
        5. 执行伏笔爽点提取
        6. 提取结尾钩子
        7. 构建 RAG 索引
        8. 更新任务状态
        """
        start_time = time.time()
        try:
            update_writing_task(apply_task_id, status="running", progress=5,
                                progress_message="开始应用创作结果...",
                                current_step="开始")
            await ws_broadcast_manager.broadcast_apply_task_update(
                script_id, {
                    "task_id": apply_task_id,
                    "chapter_index": chapter_index,
                    "phase": "started",
                    "message": "正在应用创作结果...",
                }
            )

            # 获取源任务内容
            source_task = get_writing_task(None, source_task_id)
            if not source_task:
                raise ValueError(f"源创作任务不存在，task_id={source_task_id}")

            raw_content = source_task.get("polished") or source_task.get("draft") or ""
            if not raw_content.strip():
                raise ValueError("创作结果为空")

            # 过滤内容、提取标题
            filtered_content = self._filter_chapter_content(raw_content)
            actual_title = self._extract_chapter_title(raw_content, script_id, chapter_index)

            # 保存章节
            from services.script_service import ScriptService
            script_service = ScriptService()
            script_service.add_chapter(script_id, actual_title, filtered_content,
                                        chapter_index=chapter_index)
            script_service.update_chapter_title(script_id, chapter_index, actual_title)

            self._logger.info(
                f"[WebnovelService] 应用任务 {apply_task_id}: 第{chapter_index}章已保存，标题: {actual_title}"
            )

            update_writing_task(apply_task_id, progress=30,
                                progress_message="章节内容已保存",
                                current_step="内容保存")
            await ws_broadcast_manager.broadcast_apply_task_update(
                script_id, {
                    "task_id": apply_task_id,
                    "chapter_index": chapter_index,
                    "phase": "content_saved",
                    "message": "章节已保存，正在执行后处理...",
                }
            )

            # 获取 project_id 用于后处理
            project = get_webnovel_project_by_script(script_id)
            project_id = project["id"] if project else 0

            # 构建 context_inventory 供事实记录使用
            context_inventory = self._build_context_inventory_for_apply(script_id)

            # 后处理步骤（事实记录 → 伏笔爽点提取 → 结尾钩子 → RAG 索引）
            await self._run_apply_post_process(
                apply_task_id, script_id, chapter_index, project_id,
                filtered_content, context_inventory, start_time,
            )

            # 任务归档（写流程 execution_log → pipeline_log；角色状态已并入 fact_recorder）
            await self._run_apply_archive(
                apply_task_id, script_id, chapter_index, source_task,
            )

            # 完成
            update_writing_task(apply_task_id, status="completed", progress=100,
                                progress_message="应用完成",
                                current_step="完成")
            await ws_broadcast_manager.broadcast_apply_task_update(
                script_id, {
                    "task_id": apply_task_id,
                    "chapter_index": chapter_index,
                    "phase": "completed",
                    "message": "应用完成",
                }
            )
            self._logger.info(f"[WebnovelService] 应用任务 {apply_task_id} 完成")

        except Exception as e:
            self._logger.error(f"[WebnovelService] 应用任务 {apply_task_id} 失败: {e}")
            elapsed = time.time() - start_time
            if elapsed >= _APPLY_TASK_TIMEOUT:
                error_msg = f"应用任务超时（{int(elapsed)}秒）"
            else:
                error_msg = str(e)
            update_writing_task(apply_task_id, status="failed",
                                error_message=error_msg,
                                progress_message=f"应用失败: {error_msg[:100]}",
                                current_step="失败")
            await ws_broadcast_manager.broadcast_apply_task_update(
                script_id, {
                    "task_id": apply_task_id,
                    "chapter_index": chapter_index,
                    "phase": "failed",
                    "message": "应用失败",
                    "error": error_msg,
                }
            )

    async def _run_apply_archive(
        self, apply_task_id: int, script_id: int, chapter_index: int,
        source_task: Dict[str, Any],
    ):
        """应用后置处理：任务归档（写流程 execution_log → pipeline_log）。

        角色状态记录已并入 fact_recorder 主提取（基于应用后最终内容）。
        归档失败仅记日志，不阻断应用任务完成。
        """
        try:
            from webnovel.pipeline.executors.task_archiver_executor import TaskArchiverExecutor
            execution_log = []
            ctx_raw = source_task.get("context") or ""
            if ctx_raw:
                try:
                    ctx_data = json.loads(ctx_raw)
                    execution_log = ctx_data.get("execution_log") or []
                except Exception:
                    execution_log = []
            archiver = TaskArchiverExecutor(
                script_id, chapter_index, source_task.get("id") or apply_task_id)
            arch_result = await archiver.execute({"execution_log": execution_log})
            self._logger.info(f"[WebnovelService] 应用后任务归档完成: {arch_result.step_summary}")
        except Exception as e:
            self._logger.warning(f"[WebnovelService] 应用后任务归档失败（不阻断）: {e}")
        await ws_broadcast_manager.broadcast_apply_task_update(
            script_id, {
                "task_id": apply_task_id,
                "chapter_index": chapter_index,
                "phase": "processing",
                "message": "任务归档完成",
            }
        )


    async def _run_apply_post_process(self, apply_task_id: int, script_id: int,
                                       chapter_index: int, project_id: int,
                                       filtered_content: str,
                                       context_inventory: Dict[str, Any],
                                       start_time: float):
        """执行应用任务的后处理步骤（并行优化版）。

        Phase 1: 事实记录（fact_recorder）+ 跨章节事件处理（提取/回收）+ 结尾钩子
        Phase 2: RAG 索引构建

        云端模式下 Phase 1 的 LLM 调用并发执行，延迟取最慢一个；
        本地模式下 _LOCAL_INFERENCE_LOCK 自动串行，行为不变。
        供 _execute_apply_workflow 和 retry_post_process 复用。
        """
        from webnovel.pipeline.executors.fact_recorder_executor import FactRecorderExecutor
        from webnovel.pipeline.executors.cross_chapter_event_processor_executor import (
            CrossChapterEventProcessorExecutor,
        )

        # ── Phase 1: 事实提取（事实/爽点/结尾钩子/角色状态 归口 fact_recorder）──
        update_writing_task(apply_task_id, progress=40,
                            progress_message="正在执行事实提取（事实/爽点/钩子/角色状态）...",
                            current_step="后处理")
        await ws_broadcast_manager.broadcast_apply_task_update(
            script_id, {
                "task_id": apply_task_id,
                "chapter_index": chapter_index,
                "phase": "processing",
                "message": "正在执行事实提取...",
            }
        )

        # 事实提取（fact_recorder 内部：主提取1次 + 新角色建卡1次）
        fact_executor = FactRecorderExecutor(script_id, chapter_index, apply_task_id)
        fact_result = await fact_executor.execute({
            "polished_content": filtered_content,
            "context_inventory": context_inventory,
        })
        if fact_result.success:
            self._logger.info(f"[WebnovelService] 应用任务 {apply_task_id}: 事实提取完成 - {fact_result.step_summary}")
        else:
            self._logger.warning(f"[WebnovelService] 应用任务 {apply_task_id}: 事实提取失败 - {fact_result.error_message}")

        # 跨章节事件处理（提取本章新悬念/倒计时 + 回收活跃事件；失败降级不阻断）
        event_executor = CrossChapterEventProcessorExecutor(script_id, chapter_index, apply_task_id)
        event_result = await event_executor.execute({
            "polished_content": filtered_content,
            "context_inventory": context_inventory,
        })
        if event_result.success:
            self._logger.info(f"[WebnovelService] 应用任务 {apply_task_id}: 跨章节事件处理完成 - {event_result.step_summary}")
        else:
            self._logger.warning(f"[WebnovelService] 应用任务 {apply_task_id}: 跨章节事件处理失败（已降级） - {event_result.error_message}")

        # 章节元数据（结尾钩子）由 fact_recorder._save_hook 插入，此处不再标记
        if time.time() - start_time >= _APPLY_TASK_TIMEOUT:
            raise TimeoutError("应用任务超时")

        # ── Phase 2: RAG 索引构建 ──
        update_writing_task(apply_task_id, progress=85,
                            progress_message="正在构建索引...",
                            current_step="RAG索引构建")
        await ws_broadcast_manager.broadcast_apply_task_update(
            script_id, {
                "task_id": apply_task_id,
                "chapter_index": chapter_index,
                "phase": "processing",
                "message": "正在构建索引...",
            }
        )
        if project_id:
            await self._store_rag_chunk(project_id, chapter_index, filtered_content)

    async def retry_post_process(self, script_id: int, chapter_index: int) -> Dict[str, Any]:
        """对已有内容的章节重新执行后处理（事实记录 + 伏笔爽点提取 + 结尾钩子 + RAG 索引）。

        用于应用任务后处理失败后的重试。
        """
        # 获取章节内容
        chapter = get_script_chapter(script_id, chapter_index)
        if not chapter or (chapter.get("word_count") or 0) == 0:
            return {"success": False, "error": "章节内容为空，无法重试后处理"}

        # 互斥检查
        active_tasks = (get_writing_tasks(script_id, None, "running") or []) + \
                       (get_writing_tasks(script_id, None, "pending") or [])
        for t in active_tasks:
            if t.get("task_type") == "apply":
                return {"success": False, "error": "已有应用任务正在进行中"}

        # 创建 apply 任务记录
        task = add_writing_task(script_id, chapter_index, "apply",
                                prompt=f"重试后处理：第{chapter_index}章")
        apply_task_id = task["id"]

        asyncio.create_task(
            self._execute_retry_post_process(apply_task_id, script_id, chapter_index)
        )

        return {"success": True, "task_id": apply_task_id}

    async def _execute_retry_post_process(self, apply_task_id: int, script_id: int,
                                           chapter_index: int):
        """重试后处理的异步执行流程。"""
        start_time = time.time()
        try:
            update_writing_task(apply_task_id, status="running", progress=10,
                                progress_message="开始重试后处理...",
                                current_step="开始")
            await ws_broadcast_manager.broadcast_apply_task_update(
                script_id, {
                    "task_id": apply_task_id,
                    "chapter_index": chapter_index,
                    "phase": "started",
                    "message": "正在重试后处理...",
                }
            )

            # 获取章节内容
            chapter = get_script_chapter(script_id, chapter_index)
            if not chapter:
                raise ValueError(f"章节不存在，chapter_index={chapter_index}")

            # 获取章节原文内容
            from services.script_service import ScriptService
            script_service = ScriptService()
            content_data = script_service.get_chapter_content(script_id, chapter_index)
            if not content_data or not content_data.get("content", "").strip():
                raise ValueError("章节内容为空")
            filtered_content = content_data["content"]

            # 获取 project_id
            project = get_webnovel_project_by_script(script_id)
            project_id = project["id"] if project else 0

            # 构建 context_inventory
            context_inventory = self._build_context_inventory_for_apply(script_id)

            # 广播 content_saved（章节已存在，直接跳到后处理）
            await ws_broadcast_manager.broadcast_apply_task_update(
                script_id, {
                    "task_id": apply_task_id,
                    "chapter_index": chapter_index,
                    "phase": "content_saved",
                    "message": "章节内容已确认，正在执行后处理...",
                }
            )

            # 执行后处理
            await self._run_apply_post_process(
                apply_task_id, script_id, chapter_index, project_id,
                filtered_content, context_inventory, start_time,
            )

            # 完成
            update_writing_task(apply_task_id, status="completed", progress=100,
                                progress_message="后处理完成",
                                current_step="完成")
            await ws_broadcast_manager.broadcast_apply_task_update(
                script_id, {
                    "task_id": apply_task_id,
                    "chapter_index": chapter_index,
                    "phase": "completed",
                    "message": "后处理完成",
                }
            )
            self._logger.info(f"[WebnovelService] 重试后处理任务 {apply_task_id} 完成")

        except Exception as e:
            self._logger.error(f"[WebnovelService] 重试后处理任务 {apply_task_id} 失败: {e}")
            error_msg = str(e)
            update_writing_task(apply_task_id, status="failed",
                                error_message=error_msg,
                                progress_message=f"后处理失败: {error_msg[:100]}",
                                current_step="失败")
            await ws_broadcast_manager.broadcast_apply_task_update(
                script_id, {
                    "task_id": apply_task_id,
                    "chapter_index": chapter_index,
                    "phase": "failed",
                    "message": "后处理失败",
                    "error": error_msg,
                }
            )

    def _build_context_inventory_for_apply(self, script_id: int) -> Dict[str, Any]:
        """为 apply 任务构建最小化的 context_inventory（供事实记录器使用）。"""
        project = get_webnovel_project_by_script(script_id)
        if not project:
            return {"world_settings": [], "characters": []}

        project_id = project["id"]

        # 世界观
        world_settings = []
        worldview = get_worldview_by_project(project_id)
        if worldview:
            world_settings.append({
                "name": worldview.get("name", ""),
                "summary": (worldview.get("world_summary", "") or "")[:150],
            })

        # 角色（使用与 context_inventory 一致的字段名）
        characters = []
        cards = get_character_cards_by_project(project_id)
        for card in cards:
            characters.append({
                "name": card.get("name", "") or card.get("character_name", ""),
                "type": card.get("character_type", ""),
            })

        return {
            "world_settings": world_settings,
            "characters": characters,
        }

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

    async def _generate_chapter_summary(self, project_id: int, chapter_index: int, content: str) -> str:
        """调用 LLM 生成章节的结构化摘要（200字以内）。

        返回格式化的文本，包含概要、关键事件、角色变化。
        若 LLM 调用失败则回退到机械截取。
        """
        try:
            prompt = (
                f"请为以下小说章节生成结构化摘要（总长不超过 200 字）：\n\n"
                f"【章节内容】\n{content[:3000]}\n\n"
                f"请输出严格的 JSON 格式：\n"
                f'{{"summary": "章节概要（100字以内）", '
                f'"key_events": ["事件1", "事件2"], '
                f'"character_changes": ["角色A: 变化描述"]}}'
            )
            result = await self._model_executor.execute_text_chat(
                prompt=prompt,
                system_prompt="你是一位专业的内容分析助手，擅长提取文本中的关键信息。输出严格的 JSON 格式。",
                max_tokens=400,
                script_id=0,
                project_id=project_id,
                executor_name="webnovel_service",
                prompt_name="chapter_summary",
            )
            response = result.get("content", "") if result else ""
            if not response:
                return ""

            from utils.llm_json_parser import parse_llm_json
            summary_data = parse_llm_json(
                response,
                executor_name="webnovel_service",
                prompt_name="chapter_summary",
            )
            if not summary_data:
                return ""

            # 格式化为可读文本
            parts = [f"第{chapter_index}章摘要"]
            s = summary_data.get("summary", "")
            if s:
                parts.append(f"概要: {s}")
            events = summary_data.get("key_events", [])
            if events:
                parts.append("关键事件: " + "; ".join(str(e) for e in events[:5]))
            changes = summary_data.get("character_changes", [])
            if changes:
                parts.append("角色变化: " + "; ".join(str(c) for c in changes[:5]))
            return "\n".join(parts)

        except Exception as e:
            self._logger.warning(f"[WebnovelService] LLM 生成第{chapter_index}章摘要失败，回退到机械截取: {e}")
            return ""

    async def _store_rag_chunk(self, project_id: int, chapter_index: int, content: str):
        """将章节结构化摘要存储为 RAG 片段，同时将章节原文做段落切片索引。

        只保留两类：
        1. LLM 生成的结构化摘要（chunk_type=chapter_summary）：包含概要、关键事件、角色变化
        2. 段落切片（chunk_type=chapter_paragraph）：正文细节检索

        不再写入 chunk_type=chapter（整章/机械截取）——正文量大，段落切片已能覆盖
        原文细节检索，整章索引浪费向量存储与检索资源。
        """
        try:
            from services.vector_store import get_rag_service
            rag = get_rag_service()

            # 清理当前章节的旧数据（精确删除，不影响其他章节）
            # 保留 chapter 类型的删除：存量整章索引逐步归零
            rag.delete_by_chapter_number(project_id, "chapter", chapter_index)
            rag.delete_by_chapter_number(project_id, "chapter_summary", chapter_index)

            # === 1. LLM 结构化摘要（chunk_type=chapter_summary）===
            structured_summary = await self._generate_chapter_summary(project_id, chapter_index, content)

            # === 2. 章节原文段落切片（chunk_type=chapter_paragraph）===
            # 每个 chunk 只含单个段落（精准 embedding），查询时按需扩展上下文
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            para_chunks_data = []
            if paragraphs:
                rag.delete_by_chapter_number(project_id, "chapter_paragraph", chapter_index)
                for i, para_text in enumerate(paragraphs):
                    para_chunks_data.append({
                        "content": para_text,
                        "para_index": i,
                    })

            # === 3. 构建 chunks 列表，批量计算 embedding 后一次写入 ===
            all_chunks = []

            # 添加 LLM 结构化摘要
            if structured_summary:
                all_chunks.append({
                    "content": structured_summary,
                    "chunk_type": "chapter_summary",
                    "chapter_number": chapter_index,
                    "metadata": {"chapter_index": chapter_index, "word_count": len(content)},
                })

            for pc in para_chunks_data:
                all_chunks.append({
                    "content": pc["content"],
                    "chunk_type": "chapter_paragraph",
                    "chapter_number": chapter_index,
                    "metadata": {
                        "chapter_index": chapter_index,
                        "para_index": pc["para_index"],
                        "total_paragraphs": len(paragraphs),
                    },
                })

            all_texts = [c["content"] for c in all_chunks]
            result = await self._model_executor.execute_text_to_vector(all_texts)
            all_embeddings = result.get("embeddings", [])

            if all_embeddings:
                rag.add_chunks(project_id, all_chunks, all_embeddings)

            summary_types = [c["chunk_type"] for c in all_chunks]
            self._logger.info(
                f"[WebnovelService] 第{chapter_index}章 RAG 索引完成，"
                f"共 {len(all_chunks)} 个片段（类型: {set(summary_types)}）"
            )
        except Exception as e:
            self._logger.error(f"[WebnovelService] 存储 RAG 片段失败: {e}")

    async def _index_csv_knowledge(self, project_id: int, force: bool = False):
        """将 CSV 创作知识索引到 RAG 向量库（幂等）。

        RAG 职责重定位后仅承载"无法结构化的信息"：
        - 正文细节（章节摘要/段落切片）由 _store_rag_chunk 负责
        - 创作知识（CSV 题材知识表）由本方法负责
        设定类数据（角色/世界观/力量体系/金手指/卷纲/反派/伏笔）已由
        selectable 结构化资源注入直接提供给 LLM，不再进入 RAG。

        幂等：片段写入携带 source_key（csv:{表名}:{行code}），
        RAGService.add_chunks 按 source_key 查重，重复调用不会重复写入。
        force=True 时先清空 CSV 类型再重建（手动重索引场景）。
        """
        indexed_count = 0
        pending_items = []  # [(chunk_type, content, chapter_number, metadata)]

        def _collect_one(chunk_type: str, content: str, chapter_number: int = 0, metadata: str = ""):
            """收集单条数据到待索引列表。"""
            if not content or not content.strip():
                return
            pending_items.append((chunk_type, content, chapter_number, metadata))

        try:
            # CSV 知识表（按题材加载，入 RAG 供写文/审查时语义检索）
            try:
                from webnovel.repositories.csv_knowledge_repository import (
                    query_csv_knowledge, build_csv_knowledge_chunk_text
                )
                project = get_webnovel_project(project_id)
                _csv_genre = (project.get("genre", "") or "") if project else ""

                if _csv_genre:
                    # (表名, chunk_type, genre列名)
                    _csv_tables = [
                        ("webnovel_csv_plot", "csv_plot", "applicable_genre"),
                        ("webnovel_csv_pacing", "csv_pacing", "applicable_genre"),
                        ("webnovel_csv_verdict_rules", "csv_verdict", "genre"),
                        ("webnovel_csv_scene", "csv_scene", "applicable_genre"),
                        ("webnovel_csv_writing", "csv_writing", "applicable_genre"),
                        ("webnovel_csv_naming", "csv_naming", "applicable_genre"),
                        ("webnovel_csv_character", "csv_character_knowledge", "applicable_genre"),
                        ("webnovel_csv_golden_finger", "csv_golden_finger_knowledge", "applicable_genre"),
                        ("webnovel_csv_genre_tone", "csv_genre_tone", "applicable_genre"),
                    ]
                    for table_name, chunk_type, genre_col in _csv_tables:
                        rows = query_csv_knowledge(table_name, genre=_csv_genre, genre_column=genre_col)
                        # 归一化匹配后仍无命中 → 回退全量加载（防止题材错位导致 CSV 知识静默缺失；
                        # 检索按语义不分题材，全量仅增加体积不产生错误）
                        if not rows:
                            self._logger.warning(
                                f"[WebnovelService] CSV知识 {table_name} 按题材 {_csv_genre} 无匹配，"
                                f"回退全量 {len(query_csv_knowledge(table_name, genre_column=genre_col))} 行"
                            )
                            rows = query_csv_knowledge(table_name, genre="", genre_column=genre_col)
                        for row in rows:
                            text = build_csv_knowledge_chunk_text(table_name, row)
                            if text:
                                _code = row.get("code", "")
                                _meta = json.dumps({
                                    "source": table_name,
                                    "code": _code,
                                    "genre": _csv_genre,
                                    "keywords": row.get("keywords", ""),
                                    "source_key": f"csv:{table_name}:{_code}",
                                })
                                _collect_one(chunk_type, text, metadata=_meta)
            except Exception as e:
                self._logger.warning(f"[WebnovelService] CSV知识索引失败: {e}")

            # 批量编码并写入向量库
            if pending_items:
                from services.vector_store import get_rag_service
                rag = get_rag_service()

                # force 时先清理旧 CSV 类型，否则依赖 source_key 幂等跳过
                if force:
                    for ct in {item[0] for item in pending_items}:
                        rag.delete_by_type(project_id, ct)

                # 批量调用 ModelExecutor 编码
                texts = [item[1] for item in pending_items]
                result = await self._model_executor.execute_text_to_vector(texts)
                all_embeddings = result.get("embeddings", [])

                # 构建 chunks 列表并通过 RAGService 批量写入
                if all_embeddings:
                    chunks_to_add = []
                    for chunk_type, content, chapter_number, metadata in pending_items:
                        meta_dict = {}
                        if metadata:
                            try:
                                meta_dict = json.loads(metadata) if isinstance(metadata, str) else metadata
                            except Exception:
                                meta_dict = {}
                        chunks_to_add.append({
                            "content": content,
                            "chunk_type": chunk_type,
                            "chapter_number": chapter_number,
                            "metadata": meta_dict,
                        })
                    ids = rag.add_chunks(project_id, chunks_to_add, all_embeddings)
                    indexed_count = len([i for i in ids if i > 0])

            self._logger.info(f"[WebnovelService] CSV创作知识索引完成，project_id={project_id}，共索引 {indexed_count} 条")

        except Exception as e:
            self._logger.error(f"[WebnovelService] CSV创作知识索引失败: {e}")

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

    async def get_chapter_review(self, script_id: int, chapter_index: int) -> List[Dict[str, Any]]:
        """获取章节审查结果（来自创作流水线落库的审查记录）。"""
        project = get_webnovel_project_by_script(script_id)
        if not project:
            return []

        records = get_review_records(project["id"], chapter_index)
        review_list = []
        for record in records:
            try:
                feedback = json.loads(record.get("feedback") or "{}")
            except (ValueError, TypeError):
                feedback = {}
            if not isinstance(feedback, dict):
                feedback = {}
            review_list.append({
                "dimension": record.get("review_type", ""),
                "name": feedback.get("name") or record.get("review_type", ""),
                "score": record.get("score", 0),
                "issues": feedback.get("issues", []),
                "strengths": feedback.get("strengths", []),
                "suggestions": record.get("suggestions", ""),
            })
        return review_list

    async def rollback_apply_by_chapter(self, script_id: int, chapter_index: int,
                                        project_id: int = 0) -> dict:
        """取消应用结果：按章节回退该章"应用结果"产生的全部数据。

        顺序（任一步失败不阻断后续，汇总返回）：
        1. 章节正文直接删除（script_service.delete_chapter：文件+DB行+台词）
        2. RAG 三类型 chunk 按章删除
        3. 直接删除：爽点 / 角色状态快照 / 章节时间锚点 / 世界观设定 / 执行日志 / 关系 / 成长
        4. 物品：该章获得删行、该章失去恢复持有
        5. 开放悬念：埋设章删除；回收章恢复 active
        6. 倒计时：埋设章删除；触发章恢复未触发
        7. 基础设定变更回退（角色卡）：create 删卡 / update_ability 还原 / reveal 重建旧卡
        8. 清理该章设定变更日志
        """
        summary = {"deleted": {}, "restored": {}, "rolled_back": {}, "errors": []}

        def _safe(name: str, fn, *args) -> int:
            try:
                n = fn(*args) or 0
                summary["deleted"][name] = n
                return n
            except Exception as e:
                summary["errors"].append(f"{name}: {e}")
                return 0

        def _safe_restore(name: str, fn, *args) -> int:
            try:
                n = fn(*args) or 0
                summary["restored"][name] = n
                return n
            except Exception as e:
                summary["errors"].append(f"{name}: {e}")
                return 0

        try:
            # 0. 定位项目（普通剧本无 webnovel_project 记录时仅执行正文删除）
            project = None
            if not project_id:
                project = get_webnovel_project_by_script(script_id)
                project_id = project["id"] if project else 0

            # 1. 章节正文直接删除（无论是否 webnovel 项目都执行）
            try:
                from services.script_service import get_script_service
                ok, msg = get_script_service().delete_chapter(script_id, chapter_index)
                summary["deleted"]["script_chapter"] = 1 if ok else 0
                if not ok:
                    summary["errors"].append(f"script_chapter: {msg}")
            except Exception as e:
                summary["errors"].append(f"script_chapter: {e}")

            # 非 webnovel 项目：正文已删除，跳过 webnovel 关联清理
            if not project_id:
                return summary

            # 2. RAG 三类型 chunk 删除
            try:
                from services.vector_store import get_rag_service
                rag = get_rag_service()
                for rtype in ("character", "worldview", "chapter"):
                    try:
                        n = rag.delete_by_chapter_number(project_id, rtype, chapter_index)
                        summary["deleted"][f"rag_{rtype}"] = n or 0
                    except Exception as e:
                        summary["errors"].append(f"rag_{rtype}: {e}")
            except Exception as e:
                summary["errors"].append(f"rag: {e}")

            # 3. 直接删除
            _safe("chapter_meta", delete_chapter_meta, project_id, chapter_index)
            _safe("review_record", delete_chapter_review_records, project_id, chapter_index)
            _safe("chapter_plot", delete_chapter_plot, project_id, chapter_index)
            _safe("cool_points", delete_cool_points_by_chapter, project_id, chapter_index)
            _safe("character_state", delete_character_states_by_chapter, project_id, chapter_index)
            _safe("worldview_setting", delete_worldview_settings_by_chapter, project_id, chapter_index)
            _safe("pipeline_logs", delete_pipeline_logs_by_chapter, script_id, chapter_index)
            _safe("relationships", delete_relationships_by_chapter, project_id, chapter_index)
            _safe("growths", delete_growths_by_chapter, project_id, chapter_index)
            # 章节时间锚点：按卷时间轴定位
            try:
                timelines = get_timelines_by_project(project_id)
                del_tl = 0
                for tl in timelines:
                    del_tl += delete_timeline_chapters_by_chapter(tl["id"], chapter_index) or 0
                summary["deleted"]["timeline_chapter"] = del_tl
            except Exception as e:
                summary["errors"].append(f"timeline_chapter: {e}")

            # 4. 物品：该章获得删行、该章失去恢复持有
            _safe("items_acquired", delete_items_acquired_in_chapter, project_id, chapter_index)
            _safe_restore("items_lost", restore_items_lost_in_chapter, project_id, chapter_index)

            # 5. 开放悬念：埋设章删除；回收章恢复 active
            _safe("open_loops_planted", delete_open_loops_by_planted_chapter, project_id, chapter_index)
            _safe_restore("open_loops_resolved", restore_open_loops_by_resolved_chapter,
                          project_id, chapter_index)

            # 6. 倒计时：埋设章删除；触发章恢复未触发
            _safe("countdown_planted", delete_timeline_countdowns_by_planted_chapter,
                  project_id, chapter_index)
            _safe_restore("countdown_triggered", restore_timeline_countdowns_by_trigger_chapter,
                          project_id, chapter_index)

            # 7. 基础设定变更回退（角色卡）
            changes = get_setting_changes_by_chapter(project_id, chapter_index) or []
            for ch in changes:
                try:
                    etype = str(ch.get("entity_type", "") or "")
                    ctype = str(ch.get("change_type", "") or "")
                    entity_id = ch.get("entity_id")
                    before = ch.get("before_data") or ""
                    after = ch.get("after_data") or ""
                    if etype != "character_card" or not entity_id:
                        continue
                    if ctype == "create":
                        card = get_character_card(project_id, int(entity_id))
                        if card:
                            delete_character_card(int(entity_id))
                            summary["rolled_back"][f"create:{entity_id}"] = 1
                    elif ctype == "update_ability":
                        card = get_character_card(project_id, int(entity_id))
                        if card:
                            try:
                                bd = json.loads(before)
                                prev = str(bd.get("ability_limit", "") or "")
                            except Exception:
                                prev = ""
                            update_character_card(int(entity_id), ability_limit=prev)
                            summary["rolled_back"][f"ability:{entity_id}"] = 1
                    elif ctype == "reveal":
                        try:
                            bd = json.loads(before)
                        except Exception:
                            bd = {}
                        old_card = get_character_card(project_id, int(entity_id))
                        if not old_card:
                            # 旧卡已被合并删除：按 before 快照重建
                            add_character_card(
                                project_id, str(bd.get("character_type", "supporting")),
                                name=str(bd.get("name", "")),
                                alias=str(bd.get("alias", "")),
                                identity=str(bd.get("identity", "")),
                            )
                            summary["rolled_back"][f"reveal_recreate:{entity_id}"] = 1
                        else:
                            # 改名路径：直接还原字段
                            update_character_card(
                                int(entity_id),
                                name=str(bd.get("name", "")),
                                alias=str(bd.get("alias", "")),
                                identity=str(bd.get("identity", "")),
                            )
                            summary["rolled_back"][f"reveal_restore:{entity_id}"] = 1
                except Exception as e:
                    summary["errors"].append(f"setting_change({ch.get('id')}): {e}")
            _safe("setting_changes", delete_setting_changes_by_chapter, project_id, chapter_index)

        except Exception as e:
            summary["errors"].append(f"rollback_apply_by_chapter 整体异常: {e}")
        return summary


_webnovel_service = None


def get_webnovel_service() -> WebnovelService:
    """获取网文创作服务实例。"""
    global _webnovel_service
    if _webnovel_service is None:
        _webnovel_service = WebnovelService()
    return _webnovel_service
