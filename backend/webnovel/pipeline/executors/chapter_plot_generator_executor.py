"""执行器：章节剧情生成器。

在草稿生成前，基于章节规划和上下文生成详细的场景级剧情列表，
存入 webnovel_chapter_plot 表，供草稿生成器作为核心输入。

上下文通过 ContextAnalyzer 按需组装，替代原有全量加载策略。
"""

import json
from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from ..context_analyzer import ContextAnalyzer
from core.model_executor import get_model_executor
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import (
    get_webnovel_project_by_script,
    add_chapter_plot, get_chapter_plot,
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

            # ── 通过 ContextAnalyzer 按需组装上下文 ──
            analyzer = ContextAnalyzer(script_id, chapter_index)
            step_ctx = await analyzer.analyze_and_assemble(
                step_name="chapter_plot_generator",
                inventory=context.get("context_inventory", {}),
                structural_data=context.get("structural_data", {}),
                script_id=script_id,
                project_id=project_id,
                prev_selections=context.get("step_selections"),
            )

            # 记录本步骤的选择结果，供下游步骤参考
            if "step_selections" not in context:
                context["step_selections"] = {}
            selection = step_ctx.get("_selection", {})
            context["step_selections"]["chapter_plot_generator"] = {
                "character_ids": selection.get("character_ids", []),
                "character_names": [
                    c.get("character_name", "") for c in step_ctx.get("characters", [])
                ],
                "foreshadow_ids": selection.get("foreshadow_ids", []),
                "foreshadow_contents": [
                    f.get("content", "")[:40] for f in step_ctx.get("foreshadows", [])
                ],
                "consistency_notes": selection.get("consistency_notes", []),
            }

            # ── 构建 prompt 动态 section ──
            continue_prev = "开篇需承接上一章结尾，保持剧情连贯;" if chapter_index > 1 else ""

            # 章节规划（来自 structural_data）
            chapter_plan = step_ctx.get("current_chapter_plan") or {}
            chapter_title = chapter_plan.get("chapter_title", "")
            summary = (chapter_plan.get("summary", "") or "")[:300]
            key_events = (chapter_plan.get("key_events", "") or "")[:300]
            rhythm = (chapter_plan.get("cbn", "") or "")[:100]
            plot_nodes_raw = chapter_plan.get("cpns", [])
            plot_nodes = json.dumps(plot_nodes_raw, ensure_ascii=False)[:100] if isinstance(plot_nodes_raw, list) else (plot_nodes_raw or "")[:100]
            end_node = (chapter_plan.get("cen", "") or "")[:100]
            must_cover_raw = chapter_plan.get("must_cover_nodes", [])
            must_cover_nodes = json.dumps(must_cover_raw, ensure_ascii=False)[:100] if isinstance(must_cover_raw, list) else (must_cover_raw or "")[:100]

            # 卷纲（来自 structural_data）
            current_volume = step_ctx.get("current_volume") or {}
            volume_name = current_volume.get("volume_name", "") if current_volume else ""
            volume_conflict = (current_volume.get("core_conflict", "") or "（未设定）")[:200] if current_volume else ""
            volume_goal = (current_volume.get("protagonist_goal", "") or "（未设定）")[:200] if current_volume else ""

            # 前文回顾（来自 step_ctx，由 ContextAnalyzer 按需加载）
            previous_chapters_text = self._format_previous_chapters(
                step_ctx.get("previous_chapters", []))

            # 上一章结尾状态（来自 structural_data）
            previous_hook_text = self._format_previous_hook(
                step_ctx.get("previous_hook", {}))

            # 主角（来自 step_ctx 精选的角色列表）
            protagonist_info = self._format_protagonist(step_ctx.get("characters", []))

            # 主角团（来自 step_ctx）
            character_group_info = self._format_character_group(
                step_ctx.get("character_group"))

            # 金手指（来自 step_ctx）
            golden_finger_info = self._format_golden_finger(
                step_ctx.get("golden_finger"))

            # 力量体系（来自 step_ctx）
            power_system_info = self._format_power_system(
                step_ctx.get("power_system"))

            # 世界观（来自 step_ctx）
            worldview_info = self._format_worldview(
                step_ctx.get("world_settings", []))

            # 活跃伏笔（来自 step_ctx 精选的伏笔）
            active_loops_text = self._format_foreshadows(
                step_ctx.get("foreshadows", []))

            # RAG 检索结果（来自 step_ctx）
            rag_context_text = self._format_rag_results(
                step_ctx.get("rag_results", []))

            # 一致性约束（来自 ContextAnalyzer 的 LLM 分析）
            consistency_notes = step_ctx.get("consistency_notes", [])
            consistency_text = "\n".join(f"- {note}" for note in consistency_notes) if consistency_notes else ""

            # 上章末角色状态 + 不可提前揭示的伏笔（来自 structural_data）
            character_states_text = self._format_character_states(
                step_ctx.get("last_character_states", []))
            undisclosed_text = self._format_undisclosed(
                step_ctx.get("undisclosed_foreshadows", []))

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
                previous_chapters=previous_chapters_text,
                previous_hook=previous_hook_text,
                character_states_text=character_states_text,
                undisclosed_text=undisclosed_text,
                protagonist_info=protagonist_info,
                character_group_info=character_group_info,
                golden_finger_info=golden_finger_info,
                power_system_info=power_system_info,
                worldview_info=worldview_info,
                active_loops=active_loops_text,
                rag_context=rag_context_text,
                consistency_notes=consistency_text,
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

    # ── 格式化方法 ──────────────────────────────────────────

    def _format_previous_chapters(self, previous_chapters: list) -> str:
        """格式化前文回顾文本。"""
        if not previous_chapters:
            return ""
        pc_parts = []
        for prev in previous_chapters:
            if prev.get("is_latest"):
                _c = prev["content"]
                if len(_c) > 2000:
                    _c = _c[:1000] + "\n……（中段省略）……\n" + _c[-1000:]
                pc_parts.append(f"第{prev['chapter_index']}章（上一章，请仔细承接）:\n{_c}")
            elif prev.get("is_summary"):
                pc_parts.append(prev["content"])
            else:
                pc_parts.append(f"第{prev['chapter_index']}章: {prev['content'][:300]}")
        return "\n".join(pc_parts)

    def _format_previous_hook(self, prev_hook: dict) -> str:
        """格式化上一章结尾状态。"""
        if not prev_hook or not prev_hook.get("hook_content"):
            return ""
        return (
            f"- 结尾状态: {prev_hook['hook_content']}\n"
            f"- 状态类型: {prev_hook.get('hook_type', '')}\n"
            f"- 结尾情绪: {prev_hook.get('ending_emotion', '')}"
        )

    def _format_protagonist(self, characters: list) -> str:
        """从精选角色中提取主角信息。"""
        for c in characters:
            if isinstance(c, dict) and c.get("role") in ("主角",):
                return (
                    f"- 姓名: {c.get('character_name', '')}\n"
                    f"- 身份: {c.get('identity', '')}\n"
                    f"- 性格: {c.get('personality', '')}\n"
                    f"- 缺陷: {c.get('flaw', '')}\n"
                    f"- 目标: {c.get('goals', '')}"
                )
        return ""

    def _format_character_group(self, char_group) -> str:
        """格式化主角团信息。"""
        if not char_group or not isinstance(char_group, dict):
            return ""
        cg_parts = []
        cg_goal = char_group.get("common_goal", "") or char_group.get("goal", "")
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
                ability = (m.get("key_ability", "") or "")[:50]
                flaw = (m.get("key_flaw", "") or "")[:50]
                line_parts = [f"- {name}: {role}"] if role else [f"- {name}"]
                if ability:
                    line_parts.append(f"能力: {ability}")
                if flaw:
                    line_parts.append(f"缺陷: {flaw}")
                cg_parts.append(" | ".join(line_parts))
        return "\n".join(cg_parts) if cg_parts else ""

    def _format_golden_finger(self, golden_finger) -> str:
        """格式化金手指信息。"""
        if not golden_finger or not isinstance(golden_finger, dict):
            return ""
        return (
            f"- 名称: {golden_finger.get('main_role', '')}\n"
            f"- 类型: {golden_finger.get('type', '')}\n"
            f"- 核心能力: {(golden_finger.get('core_function', '') or '')[:200]}\n"
            f"- 不可逆代价: {(golden_finger.get('irreversible_cost', '') or '')[:200]}"
        )

    def _format_power_system(self, power_system) -> str:
        """格式化力量体系信息。"""
        if not power_system or not isinstance(power_system, dict):
            return ""
        return (
            f"- 体系类型: {power_system.get('system_type', '')}\n"
            f"- 核心理念: {(power_system.get('core_creed', '') or '')[:200]}\n"
            f"- 代价规则: {(power_system.get('cost_rules', '') or '')[:200]}"
        )

    def _format_worldview(self, world_settings: list) -> str:
        """格式化世界观信息。"""
        if not world_settings:
            return ""
        parts = []
        for s in world_settings:
            if isinstance(s, dict):
                summary = s.get("world_summary", "") or s.get("content", "")
                if summary:
                    parts.append(f"- 世界简介: {summary[:200]}")
                social = s.get("social_common_sense", "")
                if social:
                    parts.append(f"- 社会常识: {social[:200]}")
                factions = s.get("factions_list", [])
                if factions:
                    faction_text = "、".join([f.get("faction_name", "") for f in factions[:5]])
                    parts.append(f"- 主要势力: {faction_text}")
        return "\n".join(parts) if parts else ""

    def _format_foreshadows(self, foreshadows: list) -> str:
        """格式化精选的伏笔列表。"""
        if not foreshadows:
            return ""
        al_parts = []
        for loop in foreshadows[:8]:
            al_parts.append(
                f"- [{loop.get('tier', '')}] {loop.get('content', '')} "
                f"(第{loop.get('planted_chapter') or loop.get('planted_ch') or 0}章埋下)"
            )
        return "\n".join(al_parts)

    def _format_rag_results(self, rag_results: list) -> str:
        """格式化 RAG 检索结果。"""
        if not rag_results:
            return ""
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
        return "\n".join(rag_parts)
