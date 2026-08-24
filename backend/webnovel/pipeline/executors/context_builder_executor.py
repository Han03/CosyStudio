"""执行器6：上下文构建器。

参考webnovel-writer的webnovel-write SKILL，实现完整的上下文构建流程。
包括：项目数据加载、角色卡片、金手指、力量体系、世界观、时间线、前文回顾等。

输出内容：
1. 项目核心设定（书名、题材、一句话简介）
2. 角色卡片（主角、配角、反派）
3. 金手指设定
4. 力量体系
5. 世界观设定
6. 卷章规划（当前卷纲、章节规划）
7. 前文回顾（最近3章）
8. 时间线信息
9. 反套路规则和硬性约束
"""

from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from repositories import get_script_characters, get_script_lines
from webnovel.repositories import (
    get_webnovel_project_by_script, get_volume_outlines_by_project,
    get_chapter_meta, get_worldview_by_project, get_power_system_by_project,
    get_golden_finger_by_project, get_villain_by_project,
    get_character_cards_by_project, get_timeline_by_project,
    get_idea_bank_by_project, get_chapter_plans_by_volume,
    get_active_open_loops,
    search_rag_chunks, add_rag_chunk, update_rag_embedding,
    get_character_group_by_project, get_character_group_members,
    get_active_character_ids,
    get_worldview_factions, get_worldview_history
)


class ContextBuilderExecutor(BaseExecutor):
    """上下文构建器执行器。"""

    step_name = "context_builder"
    step_description = "上下文构建"
    step_weight = 10

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行上下文构建。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index

            built_context = {}

            project = get_webnovel_project_by_script(script_id)
            if project:
                project_id = project["id"]

                worldview = get_worldview_by_project(project_id)
                if worldview:
                    worldview["factions_list"] = get_worldview_factions(worldview["id"])
                    worldview["history_list"] = get_worldview_history(worldview["id"])
                power_system = get_power_system_by_project(project_id)
                golden_finger = get_golden_finger_by_project(project_id)
                villain = get_villain_by_project(project_id)
                idea_bank = get_idea_bank_by_project(project_id)
                timelines = get_timeline_by_project(project_id)

                protagonists = get_character_cards_by_project(project_id, "protagonist")
                heroines = get_character_cards_by_project(project_id, "heroine")
                supporting_chars = get_character_cards_by_project(project_id, "supporting")
                all_characters = protagonists + heroines + supporting_chars

                # 过滤为活跃角色（核心角色 + 最近出场角色）
                active_ids = get_active_character_ids(project_id, chapter_index)
                if active_ids:
                    all_characters = [c for c in all_characters if c.get("id") in active_ids]

                volume_outlines = get_volume_outlines_by_project(project_id)

                current_volume = None
                volume_number = 1
                for vo in volume_outlines:
                    if vo.get("chapter_start") <= chapter_index <= vo.get("chapter_end", chapter_index):
                        current_volume = vo
                        volume_number = vo.get("volume_number", 1)
                        break

                chapter_plans = []
                if current_volume:
                    chapter_plans = get_chapter_plans_by_volume(current_volume["id"])

                current_chapter_plan = None
                for plan in chapter_plans:
                    if plan.get("chapter_index") == chapter_index:
                        current_chapter_plan = plan
                        break

                built_context["project"] = {
                    "title": project.get("title", ""),
                    "genre": project.get("genre", ""),
                    "one_liner": project.get("one_liner", ""),
                    "target_length": project.get("target_length", ""),
                    "total_volumes": project.get("total_volumes", 0),
                    "total_chapters": project.get("total_chapters", 0),
                }

                built_context["world_settings"] = [worldview] if worldview else []
                built_context["power_system"] = power_system or {}
                built_context["golden_finger"] = golden_finger or {}
                built_context["villain"] = villain or {}
                built_context["idea_bank"] = idea_bank or {}
                built_context["timelines"] = timelines or []

                built_context["characters"] = []
                for char in all_characters:
                    built_context["characters"].append({
                        "role": char.get("character_type", ""),
                        "character_name": char.get("name", ""),
                        "identity": char.get("identity", ""),
                        "personality": char.get("core_personality", ""),
                        "flaw": char.get("personality_flaw", ""),
                        "goals": char.get("true_desire", "") or char.get("long_term_goal", ""),
                        "abilities": char.get("ability_limit", ""),
                    })

                built_context["volume_outlines"] = volume_outlines
                built_context["current_volume"] = current_volume
                built_context["chapter_plans"] = chapter_plans
                built_context["current_chapter_plan"] = current_chapter_plan

                # 加载角色组及其成员，通过 character_id 关联角色卡信息
                char_group = get_character_group_by_project(project_id)
                if char_group:
                    group_members = get_character_group_members(char_group["id"])
                    card_map = {c["id"]: c for c in all_characters if c.get("id")}
                    enriched_members = []
                    for m in group_members:
                        member_info = {**m}
                        card = card_map.get(m.get("character_id"))
                        if card:
                            member_info["character_name"] = card.get("name", "")
                            member_info["personality"] = card.get("core_personality", "")
                            member_info["identity"] = card.get("identity", "")
                        enriched_members.append(member_info)
                    built_context["character_group"] = {
                        **char_group,
                        "enriched_members": enriched_members
                    }
                else:
                    built_context["character_group"] = None

            else:
                built_context["project"] = {}
                built_context["world_settings"] = []
                built_context["power_system"] = {}
                built_context["golden_finger"] = {}
                built_context["villain"] = {}
                built_context["idea_bank"] = {}
                built_context["timelines"] = []
                built_context["characters"] = get_script_characters(script_id)
                built_context["volume_outlines"] = []
                built_context["current_volume"] = None
                built_context["chapter_plans"] = []
                built_context["current_chapter_plan"] = None
                built_context["character_group"] = None

            built_context["previous_chapters"] = []
            # 优先从章节文件读取前文（script_chapters 表记录了文件路径）
            # 回退到 script_lines 表
            try:
                from services.script_service import ScriptService
                _script_svc = ScriptService()
            except Exception:
                _script_svc = None

            for i in range(max(0, chapter_index - 3), chapter_index):
                content = None
                # 1) 从章节文件读取
                if _script_svc:
                    try:
                        content = _script_svc._read_script_chapter_content(script_id, i)
                    except Exception:
                        content = None
                # 2) 回退到 script_lines
                if not content:
                    lines = get_script_lines(script_id, i)
                    if lines:
                        content = "\n".join(line["content"] for line in lines)
                if content:
                    built_context["previous_chapters"].append({
                        "chapter_index": i,
                        "content": content[:2000] if len(content) > 2000 else content,
                    })

            # 加载上一章的追读钩子
            if chapter_index > 0 and project:
                prev_meta = get_chapter_meta(project_id, chapter_index - 1)
                if prev_meta:
                    built_context["previous_hook"] = {
                        "hook_content": prev_meta.get("hook_content", ""),
                        "hook_type": prev_meta.get("hook_type", ""),
                        "hook_strength": prev_meta.get("hook_strength", ""),
                        "hook_pattern": prev_meta.get("hook_pattern", ""),
                        "ending_emotion": prev_meta.get("ending_emotion", ""),
                        "ending_location": prev_meta.get("ending_location", ""),
                    }
                else:
                    built_context["previous_hook"] = {}
            else:
                built_context["previous_hook"] = {}

            # 加载活跃伏笔
            if project:
                built_context["active_open_loops"] = get_active_open_loops(project_id)
            else:
                built_context["active_open_loops"] = []

            # 从章节规划汇总叙事线分布
            strand_summary = {}
            for plan in chapter_plans:
                s = plan.get("strand", "").strip() if isinstance(plan, dict) else ""
                if s:
                    strand_summary[s] = strand_summary.get(s, 0) + 1
            built_context["strand_summary"] = strand_summary

            current_lines = get_script_lines(script_id, chapter_index)
            if current_lines:
                built_context["current_content"] = "\n".join(line["content"] for line in current_lines)
            else:
                built_context["current_content"] = ""

            # RAG 语义检索
            built_context["rag_context"] = []
            if project and built_context["current_content"]:
                try:
                    from core.global_manager import global_manager
                    embedding_model = getattr(global_manager, 'qwen_embedding_model', None)
                    if embedding_model and embedding_model.is_loaded():
                        query_text = built_context["current_content"][:300] or \
                                     (built_context["previous_hook"].get("hook_content", "").strip() if built_context.get("previous_hook") else "")
                        if query_text:
                            embeddings = embedding_model.encode([query_text])
                            if embeddings and len(embeddings) > 0:
                                rag_results = search_rag_chunks(project_id, embeddings[0].tolist(), limit=5)
                                built_context["rag_context"] = [r["content"] for r in rag_results]
                except Exception:
                    pass

            cg = built_context.get("character_group")
            cg_member_count = len(cg.get("enriched_members", [])) if cg else 0
            summary = (
                f"上下文构建完成：世界观设定{len(built_context['world_settings'])}条，"
                f"角色{len(built_context['characters'])}个，"
                f"前文{len(built_context['previous_chapters'])}章，"
                f"卷纲{len(built_context['volume_outlines'])}卷，"
                f"活跃伏笔{len(built_context['active_open_loops'])}个，"
                f"RAG片段{len(built_context['rag_context'])}条"
                + (f"，主角团{cg_member_count}人" if cg else "")
            )
            
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "writing_context": built_context,
                    "world_settings_count": len(built_context["world_settings"]),
                    "characters_count": len(built_context["characters"]),
                    "previous_chapters_count": len(built_context["previous_chapters"]),
                    "volume_count": len(built_context["volume_outlines"]),
                    "current_chapter_plan": built_context.get("current_chapter_plan")
                }
            )
            
        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"上下文构建执行失败: {str(e)}",
                step_summary="上下文构建执行失败"
            )
