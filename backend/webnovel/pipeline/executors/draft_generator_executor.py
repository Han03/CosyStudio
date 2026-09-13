"""执行器7：草稿生成器（剧情创作）。

基于章节剧情生成器输出的详细剧情列表创作白描草稿。
上下文通过 ContextAnalyzer 按需组装，替代原有全量加载策略。

输出要求：
1. 白描草稿内容（1200-1800字），只叙述事件、行为和关键对话
2. 不写环境渲染、心理独白、五感描写和修辞
3. 遵循剧情列表中的场景顺序和事件
4. 使用JSON格式输出，包含content和chapter_title字段
"""

from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from ..context_analyzer import ContextAnalyzer
from core.model_executor import get_model_executor
from utils.llm_json_parser import parse_llm_json
from webnovel.repositories import get_webnovel_project_by_script


class DraftGeneratorExecutor(BaseExecutor):
    """草稿生成器执行器。"""

    step_name = "draft_generator"
    step_description = "草稿生成"
    step_weight = 15

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行草稿生成。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index

            user_prompt = context.get("user_prompt", "")
            chapter_plan = context.get("current_chapter_plan")

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="未找到项目信息",
                    step_summary="草稿生成失败"
                )

            project_id = project["id"]

            # ── 通过 ContextAnalyzer 按需组装上下文 ──
            analyzer = ContextAnalyzer(script_id, chapter_index)
            step_ctx = await analyzer.analyze_and_assemble(
                step_name="draft_generator",
                inventory=context.get("context_inventory", {}),
                structural_data=context.get("structural_data", {}),
                script_id=script_id,
                project_id=project_id,
                prev_selections=context.get("step_selections"),
            )

            # 记录本步骤的选择结果
            if "step_selections" not in context:
                context["step_selections"] = {}
            selection = step_ctx.get("_selection", {})
            context["step_selections"]["draft_generator"] = {
                "character_ids": selection.get("character_ids", []),
                "character_names": [
                    c.get("character_name", "") for c in step_ctx.get("characters", [])
                ],
                "consistency_notes": selection.get("consistency_notes", []),
            }

            # ── 构建剧情列表文本 ──
            chapter_plot = context.get("chapter_plot", [])
            plot_list_text = self._format_plot_list(chapter_plot, chapter_index)

            # ── 构建动态 section ──
            continue_prev = "开篇直接承接上一章结尾，不要有剧情中断感觉;" if chapter_index > 1 else ""

            # 前文回顾（来自 step_ctx）
            previous_chapters_text = self._format_previous_chapters(
                step_ctx.get("previous_chapters", []))

            # 用户要求
            user_prompt_section = ""
            if user_prompt:
                user_prompt_section = f"\n\n【用户要求】\n{user_prompt}"

            # 角色速写（来自 step_ctx 精选的角色）
            character_info = self._build_character_info(step_ctx.get("characters", []))

            # RAG 检索结果（来自 step_ctx）
            rag_context_section = self._format_rag_results(
                step_ctx.get("rag_results", []))

            # 一致性约束
            consistency_notes = step_ctx.get("consistency_notes", [])
            consistency_text = "\n".join(f"- {note}" for note in consistency_notes) if consistency_notes else ""

            # 上章末角色状态 + 不可提前揭示的伏笔
            character_states_text = self._format_character_states(
                step_ctx.get("last_character_states", []))
            undisclosed_text = self._format_undisclosed(
                step_ctx.get("undisclosed_foreshadows", []))

            # 从 .md 文件加载 prompt 模板
            prompt_data = self._load_prompt("draft_generate")
            word_cfg = (step_ctx.get("word_config") or {})
            full_prompt = prompt_data["user_prompt"].format(
                continue_prev=continue_prev,
                plot_list=plot_list_text,
                character_info=character_info,
                previous_chapters=previous_chapters_text,
                character_states_text=character_states_text,
                undisclosed_text=undisclosed_text,
                user_prompt_section=user_prompt_section,
                rag_context=rag_context_section,
                consistency_notes=consistency_text,
                draft_word_min=int(word_cfg.get("draft_word_min", 1200)),
                draft_word_max=int(word_cfg.get("draft_word_max", 1800)),
            )
            system_prompt = prompt_data["system_prompt"] or "你是一位畅销网文作家，擅长创作精彩的网络小说章节"

            executor = get_model_executor()

            result = await executor.execute_text_chat(
                prompt=full_prompt,
                system_prompt=system_prompt,
                max_tokens=max(3500, int((step_ctx.get("word_config") or {}).get("draft_word_max", 1800)) * 3),
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name=f"draft_chapter_{chapter_index}",
            )

            response_content = result.get("content", "") if result else ""

            draft_data = parse_llm_json(
                response_content,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name=f"draft_chapter_{chapter_index}",
            )

            if not draft_data or "content" not in draft_data:
                draft_data = {
                    "content": response_content.strip(),
                    "chapter_title": chapter_plan.get("chapter_title", "") if chapter_plan else f"第{chapter_index}章",
                }

            if not draft_data["content"]:
                return ExecutorResult(
                    success=False,
                    error_message="草稿生成结果为空",
                    step_summary="草稿生成失败"
                )

            word_count = len(draft_data["content"])
            
            summary = f"草稿生成完成：{word_count}字"
            
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "draft_content": draft_data["content"],
                    "chapter_title": draft_data.get("chapter_title", f"第{chapter_index}章"),
                    "word_count": word_count,
                }
            )
            
        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"草稿生成执行失败: {str(e)}",
                step_summary="草稿生成执行失败"
            )

    # ── 格式化方法 ──────────────────────────────────────────

    def _format_plot_list(self, plot_list: list, chapter_index: int) -> str:
        """将剧情列表格式化为可读文本。"""
        if not plot_list:
            return f"（第{chapter_index}章暂无详细剧情，请根据章节规划自由发挥）"

        lines = []
        for i, plot in enumerate(plot_list, 1):
            if not isinstance(plot, dict):
                continue
            scene = plot.get("scene", "")
            description = plot.get("description", "")
            characters = plot.get("characters", [])
            emotion = plot.get("emotion", "")
            conflict = plot.get("conflict", "")

            line = f"{i}. 【{scene}】"
            if description:
                line += f"\n   {description}"
            if characters:
                char_str = "、".join(characters) if isinstance(characters, list) else str(characters)
                line += f"\n   角色: {char_str}"
            if emotion:
                line += f"\n   情绪: {emotion}"
            if conflict:
                line += f"\n   冲突: {conflict}"
            lines.append(line)

        return "\n\n".join(lines)

    def _build_character_info(self, characters: list) -> str:
        """构建精选角色的速写文本。"""
        if not characters:
            return ""

        lines = ["【角色速写】"]
        for char in characters:
            if not isinstance(char, dict):
                continue
            name = char.get("character_name", "")
            if not name:
                continue
            parts = [name]
            identity = char.get("identity", "")
            if identity:
                parts.append(f"身份:{identity}")
            personality = char.get("personality", "")
            if personality:
                parts.append(f"性格:{personality}")
            flaw = char.get("flaw", "")
            if flaw:
                parts.append(f"缺陷:{flaw}")
            goals = char.get("goals", "")
            if goals:
                parts.append(f"目标:{goals}")
            # 持有物品清单
            items = char.get("items", []) or []
            item_strs = []
            for it in items:
                if not isinstance(it, dict) or not it.get("name"):
                    continue
                qty = it.get("quantity", 1) or 1
                item_strs.append(f"{it['name']}x{qty}" if qty > 1 else it["name"])
            parts.append(f"持有物品:{'、'.join(item_strs)}" if item_strs else "持有物品:无")
            lines.append(" | ".join(parts))

        lines.append(
            "物品一致性约束：角色使用、掏出、挥动任何物品前，必须已在其持有物品清单中；"
            "禁止凭空出现清单外的物品；若剧情需要新物品，必须先写获得它的过程。"
        )

        return "\n".join(lines)

    def _format_previous_chapters(self, previous_chapters: list) -> str:
        """格式化前文回顾文本。"""
        if not previous_chapters:
            return ""
        pc_parts = ["\n\n【前文回顾】"]
        for prev in previous_chapters:
            if prev.get("is_latest"):
                pc_parts.append(f"第{prev['chapter_index']}章（上一章，请仔细承接）:\n{prev['content']}")
            elif prev.get("is_summary"):
                pc_parts.append(prev["content"])
            else:
                pc_parts.append(f"第{prev['chapter_index']}章: {prev['content'][:500]}")
        return "\n".join(pc_parts)

    def _format_rag_results(self, rag_results: list) -> str:
        """格式化 RAG 检索结果。"""
        if not rag_results:
            return ""
        rag_parts = []
        for r in rag_results[:5]:
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
