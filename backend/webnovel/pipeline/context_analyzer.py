"""上下文分析器：仿 Agent 三段式装配（Analyze → Gather → Generate 输入）。

分析阶段（Analyze）：LLM 根据任务目标 + 资源目录 + RAG 候选 + 约束清单，
输出选择指令（structured_refs / rag_queries / custom_notes）。
装配阶段（Gather）：系统按选择指令从业务库加载结构化资源、执行 RAG 检索、
注入创作约束（任务输入/静态约束/数据型约束/动态约束），渲染为
assembled_context 文本与结构化字段。
生成阶段（Generate）：executor 将 assembled_context 注入节点 prompt。

失败即报错：分析失败 / 任一资源加载失败 / RAG 检索失败均抛
ContextAnalysisError，由编排器中断流程，不做任何降级。
"""

import json
import os
from typing import Dict, Any, List, Optional

from utils.logger import log_manager
from utils.llm_json_parser import parse_llm_json

from webnovel.pipeline.resource_registry import (
    RESOURCE_REGISTRY, STEP_ASSEMBLY, ContextAnalysisError,
)

# ── 步骤目标配置 ──────────────────────────────────────────────

STEP_GOALS = {
    "chapter_plot_generator": {
        "description": (
            "为第{chapter_index}章生成场景级剧情列表。"
            "需要理解章节规划目标、角色当前状态、活跃伏笔布局、前文衔接点。"
        ),
        "focus": "剧情规划覆盖、伏笔布局时机、角色弧线推进、前文自然衔接",
    },
    "draft_generator": {
        "description": (
            "根据剧情列表创作白描草稿。"
            "需要精确的角色行为参考、物品约束、前文衔接。"
        ),
        "focus": "角色行为与性格一致、物品清单约束、前文结尾自然承接、剧情完整覆盖",
    },
    "draft_reviewer": {
        "description": (
            "审查草稿质量。需要对照设定检查一致性、对照前文检查连贯性。"
        ),
        "focus": "设定一致性、角色行为合理性、剧情逻辑、前文连贯",
    },
    "draft_polisher": {
        "description": (
            "将白描草稿润色为完整小说。需要世界观氛围参考、力量体系描写参考。"
        ),
        "focus": "世界观细节准确、力量体系描写规范、文风统一",
    },
    "chapter_plot_reviewer": {
        "description": (
            "审查剧情列表质量。需要对照角色能力设定、世界观规则与伏笔布局检查合理性。"
        ),
        "focus": "设定匹配、伏笔布局合理性、剧情因果、信息揭示时机",
    },
}

# ── 各节点一致性维度清单（引导 custom_notes 输出方向）──
_STEP_DIMENSIONS = {
    "chapter_plot_generator": [
        "伏笔布局与回收时机", "角色弧线推进（性格/状态/关系）", "剧情因果与前文衔接",
        "信息揭示时机", "能力与剧情可行性", "时间空间落位",
    ],
    "draft_generator": [
        "角色行为与性格一致", "角色状态连续", "物品清单约束",
        "前文自然承接", "信息暴露边界", "能力行为边界",
    ],
    "draft_reviewer": [
        "设定一致", "角色行为合理", "剧情逻辑", "前文连贯",
        "状态与物品核对", "知识边界", "时间线",
    ],
    "draft_polisher": ["世界观细节准确", "力量体系描写规范", "文风统一"],
    "chapter_plot_reviewer": ["设定匹配（角色能力/金手指/世界观与剧情行为一致）", "伏笔布局合理性", "剧情因果与信息揭示时机"],
}

_STEP_NOTES_LIMITS = {
    "chapter_plot_generator": 5, "draft_generator": 5,
    "draft_reviewer": 3, "draft_polisher": 3,
    "chapter_plot_reviewer": 3,
}

# resource -> step_ctx 字段名（原始数据保留）
_RESOURCE_CTX_FIELD = {
    "chapter_plan": "current_chapter_plan",
    "volume_outline": "current_volume",
    "project": "project",
    "character_state": "last_character_states",
    "previous_hook": "previous_hook",
    "character_card": "characters",
    "character_group": "character_group",
    "worldview": "world_settings",
    "power_system": "power_system",
    "golden_finger": "golden_finger",
    "foreshadow": "foreshadows",
    "previous_chapter": "previous_chapters",
    "plot_list": "plot_list",
    "review_result": "review_result",
    "rag_results": "rag_results",
    "consistency_notes": "consistency_notes",
    "undisclosed_foreshadows": "undisclosed_foreshadows",
    "dimensions": "dimensions",
}

# 任务输入资源：由编排器/上游写入 task_inputs，不经 LLM 选择
_TASK_INPUT_RESOURCES = ("plot_list", "review_result")

# 数据型约束：由装配器从 structural_data 自动生成，不经 LLM 选择
_CONSTRAINT_RESOURCES = ("undisclosed_foreshadows", "dimensions", "consistency_notes")


class ContextAnalyzer:
    """上下文分析器：Analyze → Gather → Generate 输入。"""

    def __init__(self, script_id: int, chapter_index: int):
        self.script_id = script_id
        self.chapter_index = chapter_index
        self._logger = log_manager.get_logger("context_analyzer")

    # ── 主入口 ──────────────────────────────────────────────

    async def analyze_and_assemble(
        self,
        step_name: str,
        inventory: Dict[str, Any],
        structural_data: Dict[str, Any],
        script_id: int,
        project_id: int,
        prev_selections: Optional[Dict[str, Any]] = None,
        task_inputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Analyze + Gather 一步完成。失败即抛 ContextAnalysisError。"""
        env = {
            "inventory": inventory,
            "structural_data": structural_data,
            "task_inputs": task_inputs or {},
            "project_id": project_id,
            "script_id": script_id,
            "chapter_index": self.chapter_index,
        }
        selection = await self._analyze(step_name, env, prev_selections)
        step_ctx = await self._assemble_context(step_name, selection, env)
        step_ctx["_selection"] = selection
        return step_ctx

    # ── Analyze 阶段 ────────────────────────────────────────

    async def _analyze(
        self,
        step_name: str,
        env: Dict[str, Any],
        prev_selections: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """调用 LLM 分析当前步骤需要哪些上下文，返回选择指令。失败抛错。"""
        goal = STEP_GOALS.get(step_name)
        if not goal:
            raise ContextAnalysisError(f"未知步骤 {step_name}，无法分析")

        prompt_text = self._build_analysis_prompt(step_name, goal, env, prev_selections)
        if not prompt_text:
            raise ContextAnalysisError(f"步骤 {step_name} 分析 prompt 构建失败")

        system_prompt = (
            "你是一位小说创作的上下文管理专家，负责为每一步创作选择最相关的参考信息。"
            "输出严格的JSON格式。"
        )

        try:
            from core.model_executor import get_model_executor
            executor = get_model_executor()
            result = await executor.execute_text_chat(
                prompt=prompt_text,
                system_prompt=system_prompt,
                max_tokens=500,
                script_id=self.script_id,
                project_id=env["project_id"],
                executor_name="context_analyzer",
                prompt_name=f"ctx_analysis_{step_name}",
            )
            content = result.get("content", "") if result else ""
            if not content:
                raise ContextAnalysisError(f"步骤 {step_name} 上下文分析返回为空")

            selection = parse_llm_json(
                content,
                script_id=self.script_id,
                project_id=env["project_id"],
                executor_name="context_analyzer",
                prompt_name=f"ctx_analysis_{step_name}",
            )
            if not selection or not isinstance(selection, dict):
                raise ContextAnalysisError(f"步骤 {step_name} 上下文分析返回非 JSON")

            # 校验结构化引用：只允许本节点可选的资源
            assembly = STEP_ASSEMBLY.get(step_name)
            selectable = set(assembly["selectable"]) if assembly else set()
            refs = selection.get("structured_refs") or []
            if not isinstance(refs, list):
                raise ContextAnalysisError(f"步骤 {step_name} structured_refs 格式非法")
            for ref in refs:
                if not isinstance(ref, dict) or not ref.get("resource"):
                    raise ContextAnalysisError(f"步骤 {step_name} structured_refs 条目格式非法: {ref}")
                if ref["resource"] not in selectable:
                    raise ContextAnalysisError(
                        f"步骤 {step_name} 选择了本节点不可用的资源 {ref['resource']}")

            self._logger.info(
                f"[ContextAnalyzer] {step_name} 分析完成："
                f"资源{len(refs)}个，RAG查询{len(selection.get('rag_queries') or [])}条，"
                f"要点{len(selection.get('custom_notes') or [])}条"
            )
            return selection

        except ContextAnalysisError:
            raise
        except Exception as e:
            raise ContextAnalysisError(f"步骤 {step_name} 上下文分析失败: {e}")

    # ── 分析 prompt 构建 ────────────────────────────────────

    def _build_analysis_prompt(
        self,
        step_name: str,
        goal: Dict[str, Any],
        env: Dict[str, Any],
        prev_selections: Optional[Dict[str, Any]] = None,
    ) -> str:
        """构建上下文分析 prompt：任务目标 + 资源目录 + RAG 候选 + 约束 + schema。"""
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts", "context_analysis_prompt.md"
        )
        if not os.path.exists(prompt_path):
            self._logger.error(f"[ContextAnalyzer] prompt 模板不存在: {prompt_path}")
            return ""

        with open(prompt_path, "r", encoding="utf-8") as f:
            raw = f.read().strip()

        if raw.startswith("---"):
            raw = raw[3:].strip()
        if raw.endswith("---"):
            raw = raw[:-3].strip()

        user_prompt = ""
        in_user = False
        in_multi = False
        for line in raw.split("\n"):
            if line.startswith("user_prompt:"):
                in_user = True
                val = line.replace("user_prompt:", "").strip()
                if val.startswith("|"):
                    in_multi = True
                    user_prompt = ""
                else:
                    user_prompt = val
            elif in_user and in_multi:
                user_prompt += line + "\n"
            elif in_user and not in_multi:
                break
        user_prompt = user_prompt.strip()
        if not user_prompt:
            return ""

        chapter_index = self.chapter_index

        # 资源目录（按节点可选白名单裁剪展示）
        resource_catalog = self._build_resource_catalog(step_name, env)
        rag_candidates_text = self._format_rag_candidates(
            env["inventory"].get("rag_candidates", []))
        prev_step_selections_text = self._format_prev_selections(prev_selections)
        dimension_checklist_text = self._build_dimension_checklist(step_name)
        output_schema = self._build_output_schema(step_name)

        step_description = goal["description"].format(chapter_index=chapter_index)
        focus = goal["focus"]

        try:
            from utils.prompt_normalizer import normalize_text_block
            return normalize_text_block(user_prompt.format(
                chapter_index=chapter_index,
                step_name=step_name,
                step_description=step_description,
                focus=focus,
                resource_catalog=resource_catalog,
                rag_candidates_text=rag_candidates_text,
                prev_step_selections_text=prev_step_selections_text,
                dimension_checklist_text=dimension_checklist_text,
                output_schema=output_schema,
            ))
        except KeyError as e:
            self._logger.error(f"[ContextAnalyzer] prompt 占位符缺失: {e}")
            return ""

    def _build_resource_catalog(self, step_name: str, env: Dict[str, Any]) -> str:
        """按节点白名单构建资源目录文本（候选清单 + 可选深度）。"""
        assembly = STEP_ASSEMBLY.get(step_name)
        if not assembly:
            return "（无可用资源）"
        lines = []
        for res_name in assembly["selectable"]:
            res = RESOURCE_REGISTRY.get(res_name)
            if not res:
                continue
            label = res["label"]
            header = res["header"].strip("【】")
            lines.append(f"  {header}（{label}）：")
            candidate_text = self._format_resource_candidates(res_name, env)
            if candidate_text:
                lines.append(candidate_text)
            # 深度说明
            depths = list(res["formatters"].keys())
            depth_desc = {
                "full": "完整", "summary": "摘要", "tail": "结尾片段",
                "style": "文风片段", "list": "列表", "json": "JSON",
            }
            depth_hint = "，".join(
                f"{d}={depth_desc.get(d, d)}" for d in depths if d in depth_desc
            ) or "，".join(depths)
            lines.append(f"    可选深度: {depth_hint}")
        return "\n".join(lines)

    def _format_resource_candidates(self, res_name: str, env: Dict[str, Any]) -> str:
        """渲染单个资源的候选清单。"""
        inventory = env["inventory"]
        structural = env["structural_data"]

        if res_name == "character_card":
            chars = inventory.get("characters", [])
            if not chars:
                return "    （无角色）"
            return "\n".join(
                f"    [{c.get('id')}] {c.get('name')}({c.get('type')}): {c.get('summary', '')[:20]}"
                for c in chars[:20]
            )
        if res_name == "foreshadow":
            loops = inventory.get("foreshadows", [])
            if not loops:
                return "    （无活跃伏笔）"
            return "\n".join(
                f"    [{f.get('id')}] [{f.get('tier', '')}] {f.get('content', '')[:30]} "
                f"(第{f.get('planted_chapter') or 0}章)"
                for f in loops[:15]
            )
        if res_name == "worldview":
            worlds = inventory.get("world_settings", [])
            if not worlds:
                return "    （无世界观设定）"
            return "\n".join(
                f"    [{w.get('id')}] {w.get('name', '')}: {w.get('summary', '')[:40]}"
                for w in worlds[:5]
            )
        if res_name == "power_system":
            ps = inventory.get("power_system")
            if not ps:
                return "    （未设定力量体系）"
            return f"    {ps.get('name', '')}: {ps.get('summary', '')[:50]}"
        if res_name == "golden_finger":
            gf = inventory.get("golden_finger")
            if not gf:
                return "    （未设定金手指）"
            return f"    {gf.get('name', '')}: {gf.get('summary', '')[:50]}"
        if res_name == "character_group":
            cg = inventory.get("character_group")
            if not cg:
                return "    （未设定主角团）"
            return f"    {cg.get('name', '')}: 共同目标 {cg.get('goal', '')[:30]} | 成员: {cg.get('members_summary', '')[:30]}"
        if res_name == "previous_chapter":
            chapters = inventory.get("previous_chapters", [])
            if not chapters:
                return "    （无前文）"
            return "\n".join(
                f"    第{ch.get('index')}章: {ch.get('summary', '')[:40]}"
                for ch in chapters
            )
        if res_name == "chapter_plan":
            plan = structural.get("current_chapter_plan") or {}
            summary = plan.get("summary", "")[:50] if plan else ""
            return f"    本章规划概要: {summary or '（无）'}"
        if res_name == "volume_outline":
            vol = structural.get("current_volume")
            if not vol:
                return "    （无当前卷）"
            return f"    卷: {vol.get('volume_name', '')} | 核心冲突: {str(vol.get('core_conflict', ''))[:30]}"
        if res_name == "character_state":
            states = structural.get("last_character_states") or []
            if not states:
                return "    （无状态记录）"
            return "\n".join(
                f"    {st.get('character_name') or st.get('name', '?')}: 位置 {str(st.get('location', ''))[:20]} | 状态 {str(st.get('state', ''))[:40]}"
                for st in states[:10]
            )
        if res_name == "previous_hook":
            hook = structural.get("previous_hook") or {}
            if not hook.get("hook_content"):
                return "    （无钩子）"
            return f"    {hook.get('hook_content', '')[:40]}"
        if res_name == "project":
            proj = structural.get("project") or {}
            return f"    {proj.get('title', '')} | {proj.get('genre', '')}"
        return ""

    def _build_dimension_checklist(self, step_name: str) -> str:
        """按节点生成一致性维度清单文本。"""
        dims = _STEP_DIMENSIONS.get(step_name, [])
        if not dims:
            return ""
        limit = _STEP_NOTES_LIMITS.get(step_name, 5)
        lines = ["  【本节点一致性维度】"]
        for d in dims:
            lines.append(f"  - {d}")
        lines.append(f"  （本节点一致性要点请控制在 {limit} 条内）")
        return "\n".join(lines)

    def _build_output_schema(self, step_name: str) -> str:
        """按节点生成输出 JSON 格式与字段说明。"""
        assembly = STEP_ASSEMBLY.get(step_name)
        selectable = assembly["selectable"] if assembly else []
        res_labels = {
            "chapter_plan": "章节规划", "volume_outline": "当前卷纲", "project": "项目信息",
            "character_state": "上章末角色状态", "previous_hook": "上一章结尾",
            "character_card": "角色卡", "character_group": "主角团", "worldview": "世界观",
            "power_system": "力量体系", "golden_finger": "金手指", "foreshadow": "活跃伏笔",
            "previous_chapter": "前文章节",
        }
        ref_lines = []
        # 各资源的引用参数：character_card/foreshadow 用 ids，previous_chapter 用 chapter_index，其余无参
        arg_hints = {
            "character_card": '"ids": [角色id]',
            "foreshadow": '"ids": [伏笔id]',
            "previous_chapter": '"chapter_index": 章节号',
        }
        # 前文按承接需求引导 depth：剧情承接用 tail，文风参照用 style
        _PREV_CH_DEPTH_RECOMMEND = {"previous_chapter": "tail"}
        for r in selectable:
            label = res_labels.get(r, r)
            res = RESOURCE_REGISTRY.get(r, {})
            depths = list(res.get("formatters", {}).keys())
            depth_hint = " | ".join(depths) if depths else "full"
            recommend = _PREV_CH_DEPTH_RECOMMEND.get(r) or (depths[0] if depths else "full")
            arg = arg_hints.get(r, "")
            if arg:
                ref_lines.append(
                    f'    {{"resource": "{r}", {arg}, "depth": "{recommend}"}}')
            else:
                ref_lines.append(f'    {{"resource": "{r}", "depth": "{recommend}"}}')
        ref_text = "\n".join(ref_lines) if ref_lines else "    （本节点无可选资源）"

        return (
            "{\n"
            '  "structured_refs": [\n'
            f"{ref_text}\n"
            '  ],\n'
            '  "rag_queries": [{"text": "针对性查询文本", "types": ["chunk_type"], "limit": 5}],\n'
            '  "custom_notes": ["[维度] 主体: 规则"]\n'
            "}\n"
            "字段说明：\n"
            "- structured_refs 从【资源目录】选；character_card/foreshadow 必填 ids，previous_chapter 必填 chapter_index；"
            "previous_chapter 建议 depth=tail(500字)或style(320字)。\n"
            "- rag_queries：RAG 语义检索查询（含实体限定，禁止复制原文）；types：chapter/chapter_summary/foreshadow/character/worldview/power_system/golden_finger/villain/volume_outline。\n"
            "- custom_notes：一致性要点，格式「[维度名] 主体: 规则」，如「[角色状态] 苏瑶: 保持受伤未愈状态」，≤50字。\n"
        )

    def _format_rag_candidates(self, candidates: list) -> str:
        """格式化 RAG 候选清单文本。"""
        if not candidates:
            return "（无RAG候选）"
        lines = []
        for i, c in enumerate(candidates[:10]):
            doc_id = c.get("doc_id", f"rag_{i}")
            ctype = c.get("type", "")
            chapter = c.get("chapter", 0)
            preview = c.get("preview", "")[:30]
            lines.append(f"  [{doc_id}] {ctype}/第{chapter}章: {preview}")
        return "\n".join(lines)

    def _format_prev_selections(
        self, prev_selections: Optional[Dict[str, Any]]
    ) -> str:
        """格式化前序步骤的选择信息。"""
        if not prev_selections:
            return ""
        step_labels = {
            "chapter_plot_generator": "剧情生成",
            "draft_generator": "草稿生成",
            "draft_reviewer": "草稿审查",
        }
        parts = ["【前序步骤已选择的上下文】"]
        for step_name, sel in prev_selections.items():
            if not isinstance(sel, dict):
                continue
            label = step_labels.get(step_name, step_name)
            char_names = sel.get("character_names", [])
            if char_names:
                parts.append(f"{label}选择了角色: {'、'.join(char_names)}")
            notes = sel.get("consistency_notes", [])
            if notes:
                seen = set()
                for note in notes:
                    key = note if isinstance(note, str) else str(note)
                    if key in seen:
                        continue
                    seen.add(key)
                    parts.append(f"{label}标记的一致性要点: \"{note}\"")
        return "\n".join(parts) if len(parts) > 1 else ""

    # ── Gather 阶段 ─────────────────────────────────────────

    async def _assemble_context(
        self,
        step_name: str,
        selection: Dict[str, Any],
        env: Dict[str, Any],
    ) -> Dict[str, Any]:
        """按选择指令加载资源、渲染区块、组装 assembled_context。失败抛错。"""
        assembly = STEP_ASSEMBLY.get(step_name)
        if not assembly:
            raise ContextAnalysisError(f"未知步骤 {step_name}，无装配配置")

        ctx: Dict[str, Any] = {}
        sections: Dict[str, str] = {}

        # 1. 结构化资源（按 structured_refs 加载）
        refs = selection.get("structured_refs") or []
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for ref in refs:
            grouped.setdefault(ref["resource"], []).append(ref)
        for res_name, ref_list in grouped.items():
            res = RESOURCE_REGISTRY.get(res_name)
            if not res:
                raise ContextAnalysisError(f"未知资源 {res_name}")
            data_list = []
            for ref in ref_list:
                try:
                    data = res["loader"](ref, env)
                except Exception as e:
                    if isinstance(e, ContextAnalysisError):
                        raise
                    raise ContextAnalysisError(
                        f"资源 {res_name} 加载失败: {e}")
                data_list.append(data)
            depth = ref_list[0].get("depth") or res["default_depth"]
            sections[res_name] = self._render_resource(res, res_name, data_list, depth)
            # 原始数据保留到 step_ctx（合并列表）
            merged = data_list[0] if len(data_list) == 1 else data_list
            ctx[_RESOURCE_CTX_FIELD[res_name]] = merged
            if res_name == "previous_chapter":
                # 前文统一为列表结构（与旧字段兼容）
                ctx[_RESOURCE_CTX_FIELD[res_name]] = (
                    data_list if len(data_list) > 1 else data_list
                )

        # 2. 任务输入资源（不经 LLM 选择，由编排器/上游提供）
        for res_name in _TASK_INPUT_RESOURCES:
            if any(s[0] == res_name for s in assembly["sections"]):
                res = RESOURCE_REGISTRY[res_name]
                try:
                    data = res["loader"]({"depth": res["default_depth"]}, env)
                except Exception as e:
                    if isinstance(e, ContextAnalysisError):
                        raise
                    raise ContextAnalysisError(f"任务输入资源 {res_name} 加载失败: {e}")
                depth = res["default_depth"]
                # 节点可能要求特定渲染深度（如剧情审查用 json）
                for sec_name, sec_depth in assembly["sections"]:
                    if sec_name == res_name and sec_depth:
                        depth = sec_depth
                sections[res_name] = self._render_resource(res, res_name, [data], depth)
                ctx[_RESOURCE_CTX_FIELD[res_name]] = data

        # 3. 数据型约束（undisclosed_foreshadows）
        if any(s[0] == "undisclosed_foreshadows" for s in assembly["sections"]):
            undisclosed = env["structural_data"].get("undisclosed_foreshadows") or []
            sections["undisclosed_foreshadows"] = (
                RESOURCE_REGISTRY["undisclosed_foreshadows"]["formatters"]["full"](undisclosed))
            ctx["undisclosed_foreshadows"] = undisclosed

        # 4. 静态约束（审查维度）
        if any(s[0] == "dimensions" for s in assembly["sections"]):
            sections["dimensions"] = (
                RESOURCE_REGISTRY["dimensions"]["formatters"]["full"](step_name))
            ctx["dimensions"] = sections["dimensions"]

        # 5. 动态约束（consistency_notes）
        notes = selection.get("custom_notes") or []
        if not isinstance(notes, list):
            notes = [str(notes)]
        ctx["consistency_notes"] = notes
        if any(s[0] == "consistency_notes" for s in assembly["sections"]):
            sections["consistency_notes"] = (
                RESOURCE_REGISTRY["consistency_notes"]["formatters"]["full"](notes))

        # 6. RAG 检索结果
        rag_queries = selection.get("rag_queries") or []
        if not isinstance(rag_queries, list):
            rag_queries = []
        rag_results = await self._execute_rag_queries(rag_queries, env["project_id"])
        ctx["rag_results"] = rag_results
        if any(s[0] == "rag_results" for s in assembly["sections"]):
            sections["rag_results"] = (
                RESOURCE_REGISTRY["rag_results"]["formatters"]["full"](rag_results))

        # 7. 按节点区块顺序组装 assembled_context（每区块归一化，JSON 块保留缩进）
        from utils.prompt_normalizer import normalize_text_block
        _JSON_SECTIONS = {"plot_list", "review_result"}
        ordered = []
        for sec_name, _ in assembly["sections"]:
            if sec_name in sections:
                header = RESOURCE_REGISTRY[sec_name]["header"]
                body = sections[sec_name]
                if sec_name not in _JSON_SECTIONS:
                    body = normalize_text_block(body, mode="preserve_md_list")
                ordered.append(f"{header}\n{body}")
        ctx["assembled_context"] = normalize_text_block(
            "\n\n".join(ordered), mode="preserve_md_list")
        ctx["sections"] = sections
        return ctx

    def _render_resource(
        self, res: Dict[str, Any], res_name: str,
        data_list: List[Any], depth: str,
    ) -> str:
        """渲染资源区块文本（含区块标题）。"""
        formatters = res["formatters"]
        if depth not in formatters:
            depth = res["default_depth"]
        try:
            if res_name == "previous_chapter":
                # 多条前文逐条渲染
                parts = [formatters[depth](d, depth) for d in data_list]
                return "\n\n".join(parts)
            if res_name == "character_card":
                # 合并全部角色卡数据
                merged = []
                for d in data_list:
                    if isinstance(d, list):
                        merged.extend(d)
                    else:
                        merged.append(d)
                return formatters[depth](merged, depth)
            data = data_list[0] if len(data_list) == 1 else data_list
            return formatters[depth](data, depth)
        except ContextAnalysisError:
            raise
        except Exception as e:
            raise ContextAnalysisError(f"资源 {res_name} 渲染失败: {e}")

    # ── RAG 检索 ────────────────────────────────────────────

    async def _execute_rag_queries(
        self,
        queries: List[Dict[str, Any]],
        project_id: int,
    ) -> List[Dict[str, Any]]:
        """执行 LLM 生成的 RAG 查询。检索失败抛 ContextAnalysisError。"""
        if not queries:
            return []

        try:
            from services.vector_store import get_rag_service
            from core.model_executor import get_model_executor

            rag_svc = get_rag_service()
            vec_executor = get_model_executor()

            query_texts = [q.get("text", "") for q in queries if q.get("text")]
            if not query_texts:
                return []

            t2v_result = await vec_executor.execute_text_to_vector(
                query_texts, is_query=True)
            if not t2v_result or t2v_result.get("error"):
                raise ContextAnalysisError(
                    f"RAG 查询编码失败: {t2v_result.get('error') if t2v_result else '无返回'}")
            embeddings = t2v_result.get("embeddings", [])

            all_results = []
            seen = set()
            for query, emb in zip(queries, embeddings):
                if not emb:
                    continue
                chunk_types = query.get("types") or None
                limit = query.get("limit", 5)
                results = rag_svc.search(
                    project_id, emb,
                    limit=limit,
                    chunk_types=chunk_types,
                )
                for r in results:
                    from utils.prompt_normalizer import normalize_text_block
                    content = r.get("content", "")
                    dedup = content[:50] + "|" + content[-50:] if len(content) > 100 else content
                    if dedup not in seen:
                        seen.add(dedup)
                        _r = dict(r)
                        _r["content"] = normalize_text_block(content)
                        all_results.append(_r)

            return all_results[:10]

        except ContextAnalysisError:
            raise
        except Exception as e:
            raise ContextAnalysisError(f"RAG 查询失败: {e}")

