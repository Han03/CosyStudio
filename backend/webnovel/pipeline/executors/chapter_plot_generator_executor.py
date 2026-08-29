"""执行器：章节剧情生成器。

在草稿生成前，基于章节规划和上下文生成详细的场景级剧情列表，
存入 webnovel_chapter_plot 表，供草稿生成器作为核心输入。
"""

import json
from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from core.model_executor import get_model_executor
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import (
    get_webnovel_project_by_script, get_volume_outlines_by_project,
    get_character_cards_by_project, get_worldview_by_project,
    get_power_system_by_project, get_golden_finger_by_project,
    add_chapter_plot, get_chapter_plot,
    get_worldview_factions
)


class ChapterPlotGeneratorExecutor(BaseExecutor):
    """章节剧情生成器执行器。"""

    step_name = "chapter_plot_generator"
    step_description = "剧情生成"
    step_weight = 10

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行章节剧情生成。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index

            writing_context = context.get("writing_context", {})
            chapter_plan = context.get("current_chapter_plan")

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="未找到项目信息",
                    step_summary="剧情生成失败"
                )

            project_id = project["id"]

            # 检查是否已有本章剧情（避免重复生成）
            existing_plot = get_chapter_plot(project_id, chapter_index)
            if existing_plot and existing_plot.get("plot_list"):
                plot_list = existing_plot["plot_list"]
                return ExecutorResult(
                    success=True,
                    step_summary=f"使用已有剧情：{len(plot_list)}个剧情点",
                    output_data={
                        "chapter_plot": plot_list,
                        "chapter_plot_source": "cache"
                    }
                )

            # ── 构建 prompt 动态 section ──
            continue_prev = "开篇需承接上一章结尾，保持剧情连贯;" if chapter_index > 1 else ""

            # 章节规划
            chapter_title = ""
            summary = ""
            key_events = ""
            rhythm = ""
            plot_nodes = ""
            end_node = ""
            must_cover_nodes = ""
            if chapter_plan:
                chapter_title = chapter_plan.get("chapter_title", "")
                summary = chapter_plan.get("summary", "")[:300]
                key_events = chapter_plan.get("key_events", "")[:300]
                rhythm = chapter_plan.get("cbn", "")[:100]
                plot_nodes = json.dumps(chapter_plan.get("cpns", []), ensure_ascii=False)[:100]
                end_node = chapter_plan.get("cen", "")[:100]
                must_cover_nodes = json.dumps(chapter_plan.get("must_cover_nodes", []), ensure_ascii=False)[:100]

            # 卷纲
            volume_outlines = get_volume_outlines_by_project(project_id)
            current_volume = None
            for vo in volume_outlines:
                if vo.get("chapter_start") <= chapter_index <= vo.get("chapter_end", chapter_index):
                    current_volume = vo
                    break

            volume_name = current_volume.get("volume_name", "") if current_volume else ""
            volume_conflict = current_volume.get("core_conflict", "")[:200] if current_volume else ""
            volume_goal = current_volume.get("protagonist_goal", "")[:200] if current_volume else ""

            # 故事摘要（从项目数据加载）
            story_summary = project.get("story_summary", "")

            # 前文回顾：剧情生成是策划层，上一章取头尾各 1000 字兼顾起因与断点；
            # 更早章节为结构化摘要（自带标题）或开头截取回退。
            previous_chapters_text = ""
            if writing_context.get("previous_chapters"):
                pc_parts = []
                for prev in writing_context["previous_chapters"]:
                    if prev.get("is_latest"):
                        _c = prev["content"]
                        if len(_c) > 2000:
                            _c = _c[:1000] + "\n……（中段省略）……\n" + _c[-1000:]
                        pc_parts.append(f"第{prev['chapter_index']}章（上一章，请仔细承接）:\n{_c}")
                    elif prev.get("is_summary"):
                        pc_parts.append(prev["content"])
                    else:
                        pc_parts.append(f"第{prev['chapter_index']}章: {prev['content'][:300]}")
                previous_chapters_text = "\n".join(pc_parts)

            # 上一章结尾状态
            previous_hook_text = ""
            prev_hook = writing_context.get("previous_hook", {})
            if prev_hook and prev_hook.get("hook_content"):
                previous_hook_text = (
                    f"- 结尾状态: {prev_hook['hook_content']}\n"
                    f"- 状态类型: {prev_hook.get('hook_type', '')}\n"
                    f"- 结尾情绪: {prev_hook.get('ending_emotion', '')}"
                )

            # 主角
            protagonist_info = ""
            protagonists = get_character_cards_by_project(project_id, "protagonist")
            if protagonists:
                p = protagonists[0]
                protagonist_info = (
                    f"- 姓名: {p.get('name', '')}\n"
                    f"- 身份: {p.get('identity', '')}\n"
                    f"- 性格: {p.get('core_personality', '')}\n"
                    f"- 缺陷: {p.get('personality_flaw', '')}\n"
                    f"- 目标: {p.get('true_desire', '') or p.get('long_term_goal', '')}"
                )

            # 主角团
            character_group_info = ""
            char_group = writing_context.get("character_group")
            if char_group:
                cg_parts = []
                cg_goal = char_group.get("common_goal", "")
                if cg_goal:
                    cg_parts.append(f"- 共同目标: {cg_goal[:200]}")
                stage_goal = char_group.get("stage_goal", "")
                if stage_goal:
                    cg_parts.append(f"- 阶段目标: {stage_goal[:200]}")
                enriched_members = char_group.get("enriched_members", [])
                if enriched_members:
                    for m in enriched_members[:6]:
                        name = m.get("character_name") or m.get("role", f"成员{m.get('id', '')}")
                        role = m.get("role", "")
                        ability = m.get("key_ability", "")[:50]
                        flaw = m.get("key_flaw", "")[:50]
                        line_parts = [f"- {name}: {role}"] if role else [f"- {name}"]
                        if ability:
                            line_parts.append(f"能力: {ability}")
                        if flaw:
                            line_parts.append(f"缺陷: {flaw}")
                        cg_parts.append(" | ".join(line_parts))
                character_group_info = "\n".join(cg_parts)

            # 金手指
            golden_finger_info = ""
            golden_finger = get_golden_finger_by_project(project_id)
            if golden_finger:
                golden_finger_info = (
                    f"- 名称: {golden_finger.get('main_role', '')}\n"
                    f"- 类型: {golden_finger.get('type', '')}\n"
                    f"- 核心能力: {golden_finger.get('core_function', '')[:200]}\n"
                    f"- 不可逆代价: {golden_finger.get('irreversible_cost', '')[:200]}"
                )

            # 力量体系
            power_system_info = ""
            power_system = get_power_system_by_project(project_id)
            if power_system:
                power_system_info = (
                    f"- 体系类型: {power_system.get('system_type', '')}\n"
                    f"- 核心理念: {power_system.get('core_creed', '')[:200]}\n"
                    f"- 代价规则: {power_system.get('cost_rules', '')[:200]}"
                )

            # 世界观
            worldview_info = ""
            worldview = get_worldview_by_project(project_id)
            if worldview:
                worldview_info = (
                    f"- 世界简介: {worldview.get('world_summary', '')[:200]}\n"
                    f"- 社会常识: {worldview.get('social_common_sense', '')[:200]}"
                )
                # 追加势力信息
                factions = get_worldview_factions(worldview["id"])
                if factions:
                    faction_text = "、".join([f.get("faction_name", "") for f in factions[:5]])
                    worldview_info += f"\n- 主要势力: {faction_text}"

            # 活跃伏笔
            active_loops_text = ""
            active_loops = writing_context.get("active_open_loops", [])
            if active_loops:
                al_parts = []
                for loop in active_loops[:5]:
                    al_parts.append(
                        f"- [{loop.get('tier', '')}] {loop.get('content', '')} "
                        f"(第{loop.get('planted_chapter', 0)}章埋下)"
                    )
                active_loops_text = "\n".join(al_parts)

            # RAG 语义检索上下文（来自 context_builder 的多轮查询结果）
            rag_context_text = ""
            rag_results = writing_context.get("rag_context", [])
            if rag_results:
                rag_parts = []
                for r in rag_results[:8]:
                    if isinstance(r, str):
                        rag_parts.append(r[:200])
                    elif isinstance(r, dict):
                        content = r.get("content", "")[:200]
                        chunk_type = r.get("chunk_type", "")
                        ch_num = r.get("chapter_number", 0)
                        if chunk_type and ch_num:
                            rag_parts.append(f"[第{ch_num}章/{chunk_type}] {content}")
                        else:
                            rag_parts.append(content)
                rag_context_text = "\n".join(rag_parts)

            # 加载 prompt 模板并填充
            prompt_data = self._load_prompt("chapter_plot_generate")
            full_prompt = prompt_data["user_prompt"].format(
                chapter_index=chapter_index,
                continue_prev=continue_prev,
                chapter_title=chapter_title,
                summary=summary,
                key_events=key_events,
                rhythm=rhythm,
                plot_nodes=plot_nodes,
                end_node=end_node,
                must_cover_nodes=must_cover_nodes,
                volume_name=volume_name,
                volume_conflict=volume_conflict,
                volume_goal=volume_goal,
                story_summary=story_summary,
                previous_chapters=previous_chapters_text,
                previous_hook=previous_hook_text,
                protagonist_info=protagonist_info,
                character_group_info=character_group_info,
                golden_finger_info=golden_finger_info,
                power_system_info=power_system_info,
                worldview_info=worldview_info,
                active_loops=active_loops_text,
                rag_context=rag_context_text,
            )
            system_prompt = prompt_data["system_prompt"] or "你是一位资深网文策划编辑，擅长将章节规划拆解为详细的场景级剧情列表"

            executor = get_model_executor()
            result = await executor.execute_text_chat(
                prompt=full_prompt,
                system_prompt=system_prompt,
                max_tokens=3000,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name=f"chapter_plot_{chapter_index}",
            )

            response_content = result.get("content", "") if result else ""

            plot_data = parse_llm_json(
                response_content,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name=f"chapter_plot_{chapter_index}",
            )

            plot_list = []
            if plot_data and "plots" in plot_data:
                plot_list = plot_data["plots"]
            elif plot_data and isinstance(plot_data, list):
                plot_list = plot_data

            if not plot_list:
                return ExecutorResult(
                    success=False,
                    error_message="剧情生成结果为空",
                    step_summary="剧情生成失败"
                )

            # 存入数据库
            add_chapter_plot(project_id, chapter_index, plot_list)

            plot_count = len(plot_list)
            return ExecutorResult(
                success=True,
                step_summary=f"剧情生成完成：{plot_count}个剧情点",
                output_data={
                    "chapter_plot": plot_list,
                    "chapter_plot_source": "generated"
                }
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"剧情生成执行失败: {str(e)}",
                step_summary="剧情生成执行失败"
            )
