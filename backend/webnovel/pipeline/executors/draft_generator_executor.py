"""执行器7：草稿生成器（剧情创作）。

基于章节剧情生成器输出的详细剧情列表创作白描草稿。
prompt 仅包含写作要求、输出格式和剧情列表，大幅精简上下文。
草稿定位为白描骨架稿（便于后续多轮审查），文笔细节由润色阶段完成。

输出要求：
1. 白描草稿内容（1200-1800字），只叙述事件、行为和关键对话
2. 不写环境渲染、心理独白、五感描写和修辞
3. 遵循剧情列表中的场景顺序和事件
4. 使用JSON格式输出，包含content和chapter_title字段
"""

from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
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

            # ── 构建剧情列表文本 ──
            chapter_plot = context.get("chapter_plot", [])
            plot_list_text = self._format_plot_list(chapter_plot, chapter_index)

            # ── 构建动态 section ──
            continue_prev = "开篇直接承接上一章结尾，不要有剧情中断感觉;" if chapter_index > 1 else ""

            # 前文回顾：上一章由 context_builder 整章注入（已限长），不再截断；
            # 更早章节为结构化摘要（自带“第N章摘要”标题）或开头截取回退。
            writing_context = context.get("writing_context", {})
            previous_chapters_text = ""
            if writing_context.get("previous_chapters"):
                pc_parts = ["\n\n【前文回顾】"]
                for prev in writing_context["previous_chapters"]:
                    if prev.get("is_latest"):
                        pc_parts.append(f"第{prev['chapter_index']}章（上一章，请仔细承接）:\n{prev['content']}")
                    elif prev.get("is_summary"):
                        pc_parts.append(prev["content"])
                    else:
                        pc_parts.append(f"第{prev['chapter_index']}章: {prev['content'][:500]}")
                previous_chapters_text = "\n".join(pc_parts)

            # 用户要求
            user_prompt_section = ""
            if user_prompt:
                user_prompt_section = f"\n\n【用户要求】\n{user_prompt}"

            # 角色速写（本章剧情涉及的角色）
            character_info = self._build_character_info(chapter_plot, writing_context)

            # RAG 语义检索上下文（来自 context_builder 的多轮查询结果）
            rag_context_section = ""
            rag_results = writing_context.get("rag_context", [])
            if rag_results:
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
                rag_context_section = "\n".join(rag_parts)

            # 从 .md 文件加载 prompt 模板
            prompt_data = self._load_prompt("draft_generate")
            full_prompt = prompt_data["user_prompt"].format(
                continue_prev=continue_prev,
                plot_list=plot_list_text,
                character_info=character_info,
                previous_chapters=previous_chapters_text,
                user_prompt_section=user_prompt_section,
                rag_context=rag_context_section,
            )
            system_prompt = prompt_data["system_prompt"] or "你是一位畅销网文作家，擅长创作精彩的网络小说章节"

            executor = get_model_executor()

            result = await executor.execute_text_chat(
                prompt=full_prompt,
                system_prompt=system_prompt,
                max_tokens=3500,
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

    def _build_character_info(self, chapter_plot: list, writing_context: dict) -> str:
        """构建本章涉及角色的速写文本。"""
        # 从剧情列表中提取涉及的角色名
        plot_char_names = set()
        for plot in chapter_plot:
            if isinstance(plot, dict):
                chars = plot.get("characters", [])
                if isinstance(chars, list):
                    for c in chars:
                        if isinstance(c, str) and c.strip():
                            plot_char_names.add(c.strip())

        if not plot_char_names:
            return ""

        # 匹配 writing_context 中的角色数据
        characters = writing_context.get("characters", [])
        matched = []
        for char in characters:
            if not isinstance(char, dict):
                continue
            name = char.get("character_name", "")
            if name and name in plot_char_names:
                matched.append(char)

        if not matched:
            return ""

        lines = ["【角色速写】"]
        for char in matched:
            name = char.get("character_name", "")
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
            # 持有物品清单（事实记录阶段维护，无记录时明示"无"，杜绝凭空掏出物品）
            items = char.get("items", []) or []
            item_names = [
                it.get("name", "") for it in items
                if isinstance(it, dict) and it.get("name")
            ]
            parts.append(f"持有物品:{'、'.join(item_names)}" if item_names else "持有物品:无")
            lines.append(" | ".join(parts))

        lines.append(
            "物品一致性约束：角色使用、掏出、挥动任何物品前，必须已在其持有物品清单中；"
            "禁止凭空出现清单外的物品；若剧情需要新物品，必须先写获得它的过程。"
        )

        return "\n".join(lines)