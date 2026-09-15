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
from repositories.base_repository import safe_int

from webnovel.pipeline.resource_registry import (
    RESOURCE_REGISTRY, STEP_ASSEMBLY, ContextAnalysisError,
)

# ── 步骤目标配置 ──────────────────────────────────────────────

STEP_GOALS = {
    "chapter_plot_generator": {
        "name": "剧情生成",
        "description": (
            "为第{chapter_index}章生成场景级剧情列表。"
            "需要理解章节规划目标、角色当前状态、活跃伏笔布局、前文衔接点。"
        ),
        "focus": "剧情规划覆盖、伏笔布局时机、角色弧线推进、前文自然衔接",
    },
    "draft_generator": {
        "name": "草稿生成",
        "description": (
            "根据剧情列表创作白描草稿。"
            "需要精确的角色行为参考、物品约束、前文衔接。"
        ),
        "focus": "角色行为与性格一致、物品清单约束、前文结尾自然承接、剧情完整覆盖",
    },
    "draft_reviewer": {
        "name": "草稿审查",
        "description": (
            "审查草稿质量。需要对照设定检查一致性、对照前文检查连贯性。"
        ),
        "focus": "设定一致性、角色行为合理性、剧情逻辑、前文连贯",
    },
    "draft_polisher": {
        "name": "草稿润色",
        "description": (
            "将白描草稿润色为完整小说。需要世界观氛围参考、力量体系描写参考。"
        ),
        "focus": "世界观细节准确、力量体系描写规范、文风统一",
    },
    "chapter_plot_reviewer": {
        "name": "剧情审查",
        "description": (
            "审查剧情列表质量。需要对照角色能力设定、世界观规则与伏笔布局检查合理性。"
        ),
        "focus": "设定匹配、伏笔布局合理性、剧情因果、信息揭示时机",
    },
    "qa_answer": {
        "name": "知识问答",
        "description": (
            "回答用户关于小说故事状态与细节的问题。"
            "需要定位相关角色/物品/关系/前文情节与当前状态。"
        ),
        "focus": "问题定位准确、只选必要资源、宁少勿滥",
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
    "timeline": "timeline",
    "plot_list": "plot_list",
    "review_result": "review_result",
    "rag_results": "rag_results",
    "consistency_notes": "consistency_notes",
    "undisclosed_foreshadows": "undisclosed_foreshadows",
    "dimensions": "dimensions",
}

# 任务输入/约束/RAG 区块已并入 STEP_ASSEMBLY[step]["auto_sections"]，
# 由装配器统一挂载，不经 LLM 选择（详见 resource_registry.STEP_ASSEMBLY）。

# ── 分析 prompt 的【选择约束】文案（写作/问答两版）──
_WRITING_SELECTION_CONSTRAINTS = """【选择约束】（按优先级）
1. 必选：章节规划、卷纲、角色状态、上一章结尾衔接等核心资源——以【资源目录】实际列出为准；目录未列出的说明当前无内容，无需选择
2. 建议：前序步骤已选择的条目——至少保留，除非确实不相关
3. 可选：其他与本章剧情直接相关的条目——宁少勿滥
4. 深度：前文承接用 tail，文风参照用 style；角色核对细节用 full，概要用 summary；设定类用 summary
5. 参数：structured_refs 的 resource 只能取【资源目录】中列出的资源名；previous_chapter 必填 chapter_index；character_card/foreshadow 必填 ids（清单中条目编号）"""

_QA_SELECTION_CONSTRAINTS = """【选择约束】（按优先级）
1. 必选：直接回答用户问题所必需的事实类资源（角色状态、角色卡、伏笔、前文、时间轴等）——以【资源目录】实际列出为准；目录未列出的说明当前无内容，无需选择
2. 可选：补充问题细节的其他资源——宁少勿滥，避免无关资源稀释回答
3. 深度：前文承接用 tail；角色核对细节用 full，概要用 summary；设定类用 summary
4. 参数：structured_refs 的 resource 只能取【资源目录】中列出的资源名；previous_chapter 必填 chapter_index；character_card/foreshadow 必填 ids（清单中条目编号）"""

_QA_SYSTEM_PROMPT = (
    "你是一位小说知识库问答专家，负责为用户问题选择最相关的参考信息。"
    "输出严格的JSON格式。"
)

# RAG chunk_type 中文标签（用于 schema / prompt 的 types 指引动态渲染；
# 类型全集以 rag_service.ALLOWED_QUERY_TYPES 为准，此处仅提供展示标签）
_RAG_TYPE_LABELS = {
    "chapter_paragraph": "段落原文",
    "chapter_summary": "章节梗概",
    "csv_plot": "剧情模板",
    "csv_pacing": "节奏技巧",
    "csv_verdict": "裁决规则",
    "csv_scene": "场景模式",
    "csv_writing": "写作技巧",
    "csv_naming": "命名规则",
    "csv_character_knowledge": "角色知识",
    "csv_golden_finger_knowledge": "金手指设计知识",
    "csv_genre_tone": "题材基调",
}

_CHAPTER_RAG_TYPES = ("chapter_paragraph", "chapter_summary")
_CSV_RAG_TYPES = (
    "csv_plot", "csv_pacing", "csv_verdict", "csv_scene",
    "csv_writing", "csv_naming", "csv_character_knowledge",
    "csv_golden_finger_knowledge", "csv_genre_tone",
)


def _format_rag_types_guide() -> str:
    """渲染 RAG 可查 types 指引（与执行层 ALLOWED_QUERY_TYPES 保持一致）。

    分类展示：正文细节类 + 创作知识类；保留"设定类由结构化资源提供、禁止查询"约束。
    schema 与 prompt 均使用本函数输出，避免 LLM 可见清单与执行层白名单错位。
    """
    chapter_part = "、".join(
        f"{t}（{_RAG_TYPE_LABELS.get(t, t)}）" for t in _CHAPTER_RAG_TYPES)
    csv_part = "、".join(
        f"{t}（{_RAG_TYPE_LABELS.get(t, t)}）" for t in _CSV_RAG_TYPES)
    return (
        "types 可选：\n"
        f"  正文细节类：{chapter_part}\n"
        f"  创作知识类：{csv_part}\n"
        "  设定类（角色/世界观/力量体系/金手指/卷纲/反派/伏笔）已由【资源目录】"
        "结构化资源提供，禁止生成这些类型的 rag_query\n"
        "  limit 建议：chapter_paragraph 取 5~8，chapter_summary/csv_* 取 3~5"
    )


class ContextAnalyzer:
    """上下文分析器：Analyze → Gather → Generate 输入。"""

    def __init__(self, script_id: int, chapter_index: Optional[int] = None):
        # 写作流程传入章节号；问答模式（qa_answer）无章节概念，chapter_index=None
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

        system_prompt = _QA_SYSTEM_PROMPT if step_name == "qa_answer" else (
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

            # 校验结构化引用：只允许本节点可选的资源（selectable 元素为
            # "name" 或 ("name", 节点默认深度)，统一解析为资源名）
            assembly = STEP_ASSEMBLY.get(step_name)
            selectable = set()
            for item in (assembly["selectable"] if assembly else []):
                selectable.add(item[0] if isinstance(item, (list, tuple)) else item)
            refs = selection.get("structured_refs") or []
            if not isinstance(refs, list):
                raise ContextAnalysisError(f"步骤 {step_name} structured_refs 格式非法")
            for ref in refs:
                if not isinstance(ref, dict) or not ref.get("resource"):
                    raise ContextAnalysisError(f"步骤 {step_name} structured_refs 条目格式非法: {ref}")
                if ref["resource"] not in selectable:
                    raise ContextAnalysisError(
                        f"步骤 {step_name} 选择了本节点不可用的资源 {ref['resource']}")

            # 校验结构化查询：resource 必须在节点 queryable 白名单内，
            # filters 字段必须在该资源 query_filters 声明范围内
            queryable = set(assembly.get("queryable", []) if assembly else [])
            queries = selection.get("structured_queries") or []
            if not isinstance(queries, list):
                raise ContextAnalysisError(f"步骤 {step_name} structured_queries 格式非法")
            for q in queries:
                if not isinstance(q, dict) or not q.get("resource"):
                    raise ContextAnalysisError(
                        f"步骤 {step_name} structured_queries 条目格式非法: {q}")
                if q["resource"] not in queryable:
                    # 容错：LLM 偶尔把 selectable 资源误写入 structured_queries
                    # （如用 golden_finger 查询），该查询项本身无意义（selectable
                    # 资源已通过 structured_refs 注入），剔除后继续执行合法部分。
                    # 结构性错误（格式非法/无 resource）仍报错。
                    self._logger.warning(
                        f"[ContextAnalyzer] {step_name} 剔除不可查资源查询项 "
                        f"{q['resource']}（不可 structured_queries，仅可 structured_refs 选择）")
                    continue
                res = RESOURCE_REGISTRY.get(q["resource"])
                allowed = set(res.get("query_filters", [])) if res else set()
                # 非法 filters 字段剔除（保留合法字段继续执行），不中断创作：
                # LLM 偶尔会用错过滤字段（如 timeline 用 keyword），查询只是参考检索，
                # 剔除后仍可执行；结构性错误（resource 不可查/格式非法）仍报错。
                f_raw = q.get("filters") or {}
                f_clean = {k: v for k, v in f_raw.items() if k in allowed}
                if f_clean != f_raw:
                    dropped = sorted(set(f_raw) - set(f_clean))
                    self._logger.warning(
                        f"[ContextAnalyzer] {step_name} 查询 {q['resource']} 剔除非法"
                        f" filters 字段: {dropped}（允许: {'/'.join(sorted(allowed))}）")
                q["filters"] = f_clean
                limit = q.get("limit")
                if limit is not None:
                    try:
                        limit = int(limit)
                    except (TypeError, ValueError):
                        limit = 5  # 非法 limit 回落默认 5，不中断
                        q["limit"] = limit
                    if not (1 <= limit <= 10):
                        limit = 5  # 超范围回落默认 5，不中断
                        q["limit"] = limit

            self._logger.info(
                f"[ContextAnalyzer] {step_name} 分析完成："
                f"资源{len(refs)}个，结构化查询{len(queries)}条，"
                f"RAG查询{len(selection.get('rag_queries') or [])}条，"
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
        is_qa = (step_name == "qa_answer")

        # 任务上下文首句（写作/问答两版）
        if is_qa:
            question = (env.get("task_inputs") or {}).get("question", "")
            task_context_line = (
                f"你正在为用户问题「{question}」选择回答所需的参考信息。" if question
                else "你正在为用户问题选择回答所需的参考信息。"
            )
        else:
            task_context_line = (
                f"你正在为第{chapter_index}章的【{goal['name']}】步骤选择参考上下文。"
            )

        # 资源目录（按节点可选白名单裁剪展示）
        resource_catalog = self._build_resource_catalog(step_name, env)
        rag_candidates_text = self._format_rag_candidates(
            env["inventory"].get("rag_candidates", []))
        prev_step_selections_text = self._format_prev_selections(prev_selections)
        dimension_checklist_text = self._build_dimension_checklist(step_name)
        output_schema = self._build_output_schema(step_name, env)
        selection_constraints_text = (
            _QA_SELECTION_CONSTRAINTS if is_qa else _WRITING_SELECTION_CONSTRAINTS
        )

        step_description = goal["description"].format(chapter_index=chapter_index)
        focus = goal["focus"]

        try:
            from utils.prompt_normalizer import normalize_text_block
            return normalize_text_block(user_prompt.format(
                chapter_index=chapter_index,
                step_name=goal["name"],
                task_context_line=task_context_line,
                step_description=step_description,
                focus=focus,
                resource_catalog=resource_catalog,
                rag_candidates_text=rag_candidates_text,
                prev_step_selections_text=prev_step_selections_text,
                dimension_checklist_text=dimension_checklist_text,
                selection_constraints_text=selection_constraints_text,
                rag_types_guide=_format_rag_types_guide(),
                output_schema=output_schema,
            ))
        except KeyError as e:
            self._logger.error(f"[ContextAnalyzer] prompt 占位符缺失: {e}")
            return ""

    def _build_resource_catalog(self, step_name: str, env: Dict[str, Any]) -> str:
        """按节点可选白名单构建资源目录文本（资源编号 + 候选清单 + 深度）。

        只列出当前有实际内容的资源：候选为空（空态/无数据）的资源整条跳过，
        保证目录 = 可选项 = 注入内容，避免 LLM 误选空资源。

        编号即引用键：character_card/foreshadow 的条目编号 = structured_refs 的 ids；
        previous_chapter 的"第N章" = chapter_index。输出 schema 与目录一一对应。
        """
        assembly = STEP_ASSEMBLY.get(step_name)
        if not assembly:
            return "（无可用资源）"
        depth_desc = {
            "full": "完整", "summary": "摘要", "tail": "结尾片段",
            "style": "文风片段", "list": "列表", "json": "JSON",
        }
        lines = []
        idx = 0
        for item in assembly.get("selectable", []):
            res_name = item[0] if isinstance(item, (list, tuple)) else item
            res = RESOURCE_REGISTRY.get(res_name)
            if not res:
                continue
            candidate_text = self._format_resource_candidates(res_name, env)
            if not candidate_text.strip():
                # 空资源不列目录
                continue
            idx += 1
            header = res["header"].strip("【】")
            label = res["label"]
            title = f"{header}" + (f" {label}" if label and label != header else "")
            # 可查询资源：目录仅列热点，全量/筛选用 structured_queries
            if res_name in (assembly.get("queryable") or []):
                title += "（更多用查询）"
            depths = list(res["formatters"].keys())
            depth_hint = " / ".join(
                f"{d}={depth_desc.get(d, d)}" for d in depths if d in depth_desc
            ) or " / ".join(depths)
            line = f"{idx}. {title}"
            if depth_hint:
                line += f" | 深度: {depth_hint}"
            lines.append(line)
            for cl in candidate_text.split("\n"):
                lines.append(cl)
        # 目录定位 = 重要/热点锚点；全量数据一律走 structured_queries
        if lines and assembly.get("queryable"):
            lines.append(
                "（目录仅显示重要/热点信息；未列出的角色、历史章节、伏笔等全量数据请用 structured_queries 按条件查询）")
        return "\n".join(lines) if lines else "（无可用资源）"

    def _format_resource_candidates(self, res_name: str, env: Dict[str, Any]) -> str:
        """渲染单个资源的候选清单。"""
        inventory = env["inventory"]
        structural = env["structural_data"]

        if res_name == "character_card":
            chars = inventory.get("characters", [])
            if not chars:
                return ""
            # 热点：仅主角+核心角色前 4（env 已按主角优先排序）；其他角色用查询
            # 主次结构：名字（类型）为主，id= 为引用键辅助，— 后为详情
            return "\n".join(
                f"    - {c.get('name')}（{c.get('type')}）id={c.get('id')} — {c.get('summary', '')[:40]}"
                for c in chars[:4]
            )
        if res_name == "foreshadow":
            loops = inventory.get("foreshadows", [])
            if not loops:
                return ""
            # 热点排序：核心 tier 优先，同 tier 最近埋设靠前；仅列前 4
            tier_rank = {"核心": 0, "重要": 1, "支线": 2}
            loops = sorted(loops, key=lambda f: (
                tier_rank.get(str(f.get("tier", "")), 9),
                -(f.get("planted_chapter") or 0),
            ))
            # 主次结构：tier 标签 + 内容为主，id= 为引用键辅助，埋设章为定位信息
            return "\n".join(
                f"    - [{f.get('tier', '')}] {f.get('content', '')[:40]} id={f.get('id')} "
                f"（第{f.get('planted_chapter') or 0}章埋下）"
                for f in loops[:4]
            )
        if res_name == "worldview":
            worlds = inventory.get("world_settings", [])
            if not worlds:
                return ""
            lines = []
            for w in worlds[:5]:
                w_name = w.get('name', '') or ''
                w_summary = w.get('summary', '') or ''
                if not w_name and not w_summary:
                    continue
                lines.append(f"    - {w_name} — {w_summary[:40]}")
            return "\n".join(lines)
        if res_name == "power_system":
            ps = inventory.get("power_system")
            if not ps or not (ps.get('name') or ps.get('summary')):
                return ""
            return f"    - {ps.get('name', '')} — {ps.get('summary', '')[:50]}"
        if res_name == "golden_finger":
            gf = inventory.get("golden_finger")
            if not gf or not (gf.get('name') or gf.get('summary')):
                return ""
            return f"    - {gf.get('name', '')} — {gf.get('summary', '')[:50]}"
        if res_name == "character_group":
            cg = inventory.get("character_group")
            if not cg:
                return ""
            cg_name = cg.get('name', '') or ''
            cg_goal = cg.get('goal', '') or ''
            cg_members = cg.get('members_summary', '') or ''
            if not cg_name and not cg_goal and not cg_members:
                return ""
            head = f"{cg_name}: " if cg_name else ""
            return f"    - {head}共同目标 {cg_goal[:30]} | 成员: {cg_members[:30]}"
        if res_name == "previous_chapter":
            chapters = inventory.get("previous_chapters", [])
            if not chapters:
                return ""
            chapters = sorted(chapters, key=lambda c: c.get("index") or 0)
            # 热点：仅最近 2 章（承接锚点）；更早章节用 chapter_index/查询
            window = chapters[-2:]
            lines = [
                f"    - 第{ch.get('index')}章 — {str(ch.get('summary', '')).replace(chr(10), ' ')[:60]}"
                for ch in window
            ]
            if len(chapters) > len(window):
                lines.append(
                    f"（仅列最近 {len(window)} 章；更早章节用 structured_queries 或指定 chapter_index 获取）")
            return "\n".join(lines)
        if res_name == "chapter_plan":
            plan = structural.get("current_chapter_plan") or {}
            summary = plan.get("summary", "")[:50] if plan else ""
            return "" if not summary else f"    - 本章规划概要: {summary}"
        if res_name == "volume_outline":
            vol = structural.get("current_volume")
            if not vol:
                return ""
            return f"    - 卷: {vol.get('volume_name', '')} | 核心冲突: {str(vol.get('core_conflict', ''))[:30]}"
        if res_name == "character_state":
            states = structural.get("last_character_states") or []
            if not states:
                return ""
            return "\n".join(
                f"    - {st.get('character_name') or st.get('name', '?')} — "
                f"位置 {str(st.get('location', ''))[:20]} | "
                f"状态 {(str(st.get('state_summary') or st.get('state', '')))[:40]}"
                for st in states[:6]
            )
        if res_name == "previous_hook":
            hook = structural.get("previous_hook") or {}
            if not hook.get("hook_content"):
                return ""
            return f"    - {hook.get('hook_content', '')[:40]}"
        if res_name == "project":
            proj = structural.get("project") or {}
            return f"    - {proj.get('title', '')} | {proj.get('genre', '')}"
        if res_name == "timeline":
            from webnovel.repositories import get_timelines_by_project, get_timeline_chapters
            timelines = get_timelines_by_project(env["project_id"])
            if not timelines:
                return ""
            # 热点：仅当前创作卷的时间线（写作锚点）；其他卷用查询
            cur_vol = (structural.get("current_volume") or {}).get("volume_number")
            target = None
            for tl in timelines:
                if tl.get("volume_number") == cur_vol:
                    target = tl
                    break
            if target is None:
                target = timelines[-1]
            lines = []
            chapters = get_timeline_chapters(target["id"]) or []
            recent = chapters[-1] if chapters else {}
            anchor = (recent.get("time_anchor", "") or "")[:20]
            lines.append(
                f"    - 第{target.get('volume_number', '?')}卷: 基准 {str(target.get('time_base', ''))[:30]}"
                f" | {len(chapters)}章 | 最近锚点 {anchor}"
            )
            return "\n".join(lines)
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

    def _build_output_schema(self, step_name: str, env: Dict[str, Any]) -> str:
        """按节点生成输出 JSON 格式与字段说明。

        structured_refs 示例行只列出【资源目录】中实际有内容的资源：
        空资源（如第 1 章尚无活跃伏笔）不出现示例行，杜绝 LLM 按示例
        幻觉选择不存在的资源（此前出现过 LLM 编造伏笔 id 导致装配报错）。
        """
        assembly = STEP_ASSEMBLY.get(step_name)
        selectable = assembly["selectable"] if assembly else []
        queryable = assembly.get("queryable", []) if assembly else []
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
        for item in selectable:
            r = item[0] if isinstance(item, (list, tuple)) else item
            # 与资源目录同源判空：目录中未列出的空资源不在 schema 示例中出现
            if not self._format_resource_candidates(r, env).strip():
                continue
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

        # 可查询资源清单（structured_queries 白名单）
        if queryable:
            query_example = (
                '    {"resource": "' + (queryable[0] if queryable else "character_card")
                + '", "filters": {"keyword": "关键词"}, "text": "查询意图", "limit": 5}'
            )
            query_section = (
                '  "structured_queries": [\n'
                f"{query_example}\n"
                '  ],\n'
            )
            # 各可查询资源的用途与 filters 明细（主字段用名字标识，id 辅助）
            query_res_lines = []
            for r in queryable:
                res = RESOURCE_REGISTRY.get(r, {})
                label = res.get("label", r)
                filters = res.get("query_filters", [])
                filter_desc = {
                    "character": "角色名", "keyword": "内容关键词", "ids": "角色id列表（辅助）",
                    "chapter": "章号", "character_id": "角色id（辅助）", "type": "角色类型",
                    "status": "active/resolved", "tier": "层级", "volume": "卷号（辅助）",
                    "volume_name": "卷名", "scene": "场景名", "characters": "角色名",
                    "emotion": "情绪", "relation_type": "关系类型", "cool_point_type": "爽点类型",
                    "villain": "反派名", "only_held": "仅持有中",
                    "thread_type": "主线/支线", "era": "时代", "name": "设定名",
                    "category": "类别", "entity_type": "变更对象类型",
                    "entity_id": "对象id（辅助）", "level_name": "境界名",
                }
                f_desc = "、".join(
                    f"{f}={filter_desc.get(f, f)}" + ("（优先）" if f in (
                        "character", "volume_name", "villain", "keyword",
                        "name", "era", "level_name") else "")
                    for f in filters)
                query_res_lines.append(f"    - {label}（{r}）: {f_desc}")
            query_res_text = "\n".join(query_res_lines)
            query_note = (
                "structured_queries 可查资源与过滤条件：\n"
                f"{query_res_text}\n"
                "规则：过滤优先用角色名/卷名/场景名等自然标识（模糊匹配即可），id 仅当你确知时使用；"
                "resource 只能取上述类型，filters 仅支持对应资源列出的字段；"
                "能通过 structured_refs 精确选择的优先用 structured_refs；一般 0~3 条；"
                "text 简述查询意图供追溯。\n"
            )
        else:
            query_section = '  "structured_queries": [],\n'
            query_note = "- structured_queries：本节点不支持结构化查询，保持空数组。\n"

        return (
            "{\n"
            '  "structured_refs": [\n'
            f"{ref_text}\n"
            '  ],\n'
            f"{query_section}"
            '  "rag_queries": [{"text": "针对性查询文本", "types": ["chunk_type"], "limit": 5}],\n'
            '  "custom_notes": ["[维度] 主体: 规则"]\n'
            "}\n"
            "字段说明：\n"
            "- structured_refs 只能从【资源目录】实际列出的资源中选择（示例行即当前有数据的全部可选项）；"
            "目录未列出的资源（当前无数据）不可选择。`id=` 后的数字即引用键：character_card/foreshadow 的 ids 直接使用目录中 id= 后的数字；"
            "previous_chapter 的 chapter_index 使用目录中的第N章章节号；previous_chapter 建议 depth=tail(500字)或style(320字)。\n"
            f"{query_note}"
            "- rag_queries：RAG 语义检索查询（含实体限定，禁止复制原文）；"
            + _format_rag_types_guide().replace("\n", "\n  ") + "\n"
            "- custom_notes：一致性要点，格式「[维度名] 主体: 规则」，如「[角色状态] 苏瑶: 保持受伤未愈状态」，≤50字。\n"
        )

    def _format_rag_candidates(self, candidates: list) -> str:
        """格式化 RAG 候选清单文本。"""
        if not candidates:
            return (
                "（无预检索候选）RAG 库已索引已创作章节的正文段落(chapter_paragraph)"
                "与章节梗概(chapter_summary)，原文细节类问题（对话/价格/具体情节）"
                "请用 rag_queries 主动检索；设定类数据已由【资源目录】提供，无需检索"
            )
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
        parts = ["【前序步骤已选择的上下文】"]
        for step_name, sel in prev_selections.items():
            if not isinstance(sel, dict):
                continue
            goal = STEP_GOALS.get(step_name)
            label = goal["name"] if goal else step_name
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
        """按选择指令加载资源、渲染区块、组装 assembled_context。失败抛错。

        selectable 单源控制：LLM 选中的结构化资源（refs ∈ selectable）100% 注入，
        按 selectable 顺序组装；auto_sections（任务输入/约束/RAG）固定挂载追加在后。
        """
        assembly = STEP_ASSEMBLY.get(step_name)
        if not assembly:
            raise ContextAnalysisError(f"未知步骤 {step_name}，无装配配置")

        # 解析 selectable：元素为 "name" 或 ("name", 节点默认深度)
        selectable_items: List[Tuple[str, Optional[str]]] = []
        for item in assembly.get("selectable", []):
            if isinstance(item, (list, tuple)):
                selectable_items.append((item[0], item[1] if len(item) > 1 else None))
            else:
                selectable_items.append((item, None))
        selectable_names = {name for name, _ in selectable_items}
        auto_items = assembly.get("auto_sections", [])

        ctx: Dict[str, Any] = {}
        sections: Dict[str, str] = {}
        injected_keys: Dict[str, set] = {}

        # 1. 结构化资源（按 structured_refs 加载；LLM 选中即注入，无过滤）
        refs = selection.get("structured_refs") or []
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for ref in refs:
            grouped.setdefault(ref["resource"], []).append(ref)
        for res_name, ref_list in grouped.items():
            res = RESOURCE_REGISTRY.get(res_name)
            if not res:
                raise ContextAnalysisError(f"未知资源 {res_name}")
            # previous_chapter 深度规约：full 仅限最近 2 章，更早章节强制 tail
            # （防注入膨胀：旧章全文进创作 prompt）。规约须在 loader 执行前修改 ref。
            if res_name == "previous_chapter" and env.get("chapter_index"):
                cur_ch = safe_int(env["chapter_index"])
                for ref in ref_list:
                    rch = safe_int(ref.get("chapter_index"))
                    if (rch > 0 and rch < cur_ch - 2
                            and ref.get("depth") == "full"):
                        self._logger.info(
                            f"[ContextAnalyzer] 第{rch}章 previous_chapter depth=full "
                            f"规约为 tail（仅最近 2 章可全文注入）")
                        ref["depth"] = "tail"
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
            # 深度：LLM 显式 depth → 节点默认深度（selectable tuple）→ 资源默认深度
            depth = ref_list[0].get("depth") or ""
            if depth not in res["formatters"]:
                depth = dict(selectable_items).get(res_name) or res["default_depth"]
            sections[res_name] = self._render_resource(res, res_name, data_list, depth)
            # 原始数据保留到 step_ctx（合并列表）
            merged = data_list[0] if len(data_list) == 1 else data_list
            ctx[_RESOURCE_CTX_FIELD[res_name]] = merged
            if res_name == "previous_chapter":
                # 前文统一为列表结构（与旧字段兼容）
                ctx[_RESOURCE_CTX_FIELD[res_name]] = (
                    data_list if len(data_list) > 1 else data_list
                )
            # 去重键收集：记录已注入条目的 dedup_key 值，
            # 供结构化查询结果渲染前过滤重合条目（P1：避免同一信息重复注入）
            dk = res.get("dedup_key")
            if dk:
                keys = set()
                for item in data_list:
                    if isinstance(item, dict) and item.get(dk) is not None:
                        keys.add(str(item.get(dk)))
                    elif isinstance(item, list):
                        for sub in item:
                            if isinstance(sub, dict) and sub.get(dk) is not None:
                                keys.add(str(sub.get(dk)))
                if keys:
                    injected_keys[res_name] = keys

        # 1.5 结构化主动查询（structured_queries：动态检索业务库全量数据）
        # 结果渲染为独立区块【资源名·查询】，追加在 selectable 区块之后、auto 之前；
        # 查询失败抛错；空结果跳过区块（合法查询无命中不报错）。
        # 去重：查询命中条目若与已注入 selectable 资源重合（dedup_key 相同）则过滤，
        # 避免同一信息在资源块与查询块重复出现。
        query_blocks: List[str] = []
        query_results: Dict[str, List[Dict[str, Any]]] = {}
        queries = selection.get("structured_queries") or []
        if not isinstance(queries, list):
            queries = []
        for q in queries:
            if not isinstance(q, dict):
                raise ContextAnalysisError(f"structured_queries 条目格式非法: {q}")
            res_name = q.get("resource")
            res = RESOURCE_REGISTRY.get(res_name)
            if not res or not res.get("query_loader"):
                raise ContextAnalysisError(f"不可查询的资源 {res_name}")
            try:
                data = res["query_loader"](q, env)
            except ContextAnalysisError:
                raise
            except Exception as e:
                raise ContextAnalysisError(
                    f"结构化查询 {res_name} 失败: {e}")
            dk = res.get("dedup_key")
            if dk:
                prior = injected_keys.get(res_name) or set()
                if prior:
                    data = [
                        d for d in data
                        if not (isinstance(d, dict) and d.get(dk) is not None
                                and str(d.get(dk)) in prior)
                    ]
            query_results[res_name] = data or []
            if not data:
                continue
            formatters = res["formatters"]
            depth = q.get("depth") or res["default_depth"]
            if depth not in formatters:
                depth = res["default_depth"]
            body = formatters[depth](data, depth)
            if not body or not body.strip():
                continue
            query_blocks.append(f"{res['header']}·查询\n{body}")
        ctx["structured_query_results"] = query_results
        if query_blocks:
            sections["__query_blocks__"] = "\n\n".join(query_blocks)

        # 2. auto_sections 固定挂载（任务输入/约束/RAG，按配置顺序）
        for sec_name, sec_depth in auto_items:
            res = RESOURCE_REGISTRY.get(sec_name)
            if not res:
                raise ContextAnalysisError(f"未知资源 {sec_name}（auto_sections）")
            if res.get("task_input"):
                # 任务输入资源：由编排器/上游写入，不经 LLM 选择
                try:
                    data = res["loader"]({"depth": sec_depth or res["default_depth"]}, env)
                except Exception as e:
                    if isinstance(e, ContextAnalysisError):
                        raise
                    raise ContextAnalysisError(f"任务输入资源 {sec_name} 加载失败: {e}")
                sections[sec_name] = self._render_resource(
                    res, sec_name, [data], sec_depth or res["default_depth"])
                ctx[_RESOURCE_CTX_FIELD[sec_name]] = data
            elif sec_name == "undisclosed_foreshadows":
                # 数据型约束
                undisclosed = env["structural_data"].get("undisclosed_foreshadows") or []
                sections[sec_name] = res["formatters"]["full"](undisclosed)
                ctx[sec_name] = undisclosed
            elif sec_name == "dimensions":
                # 静态约束（审查维度）
                sections[sec_name] = res["formatters"]["full"](step_name)
                ctx[sec_name] = sections[sec_name]
            elif sec_name == "consistency_notes":
                # 动态约束（custom_notes 回注）
                notes = selection.get("custom_notes") or []
                if not isinstance(notes, list):
                    notes = [str(notes)]
                ctx[sec_name] = notes
                sections[sec_name] = res["formatters"]["full"](notes)
            elif sec_name == "rag_results":
                # RAG 检索结果（rag_queries 产物）
                rag_queries = selection.get("rag_queries") or []
                if not isinstance(rag_queries, list):
                    rag_queries = []
                rag_results = await self._execute_rag_queries(rag_queries, env["project_id"])
                ctx[sec_name] = rag_results
                sections[sec_name] = res["formatters"]["full"](rag_results)
            else:
                raise ContextAnalysisError(
                    f"未知 auto_sections 区块类型: {sec_name}")

        # 3. 组装 assembled_context：selectable 命中项（按 selectable 顺序）
        #    + structured_queries 查询结果 + auto 项（按配置顺序）
        from utils.prompt_normalizer import normalize_text_block
        _JSON_SECTIONS = {"plot_list", "review_result"}
        ordered = []
        for sec_name, _ in selectable_items:
            if sec_name in sections:
                ordered.append(sec_name)
        if "__query_blocks__" in sections:
            ordered.append("__query_blocks__")
        for sec_name, _ in auto_items:
            if sec_name in sections:
                ordered.append(sec_name)
        ordered_parts = []
        for sec_name in ordered:
            if sec_name == "__query_blocks__":
                ordered_parts.append(sections[sec_name])
                continue
            header = RESOURCE_REGISTRY[sec_name]["header"]
            body = sections[sec_name]
            if sec_name not in _JSON_SECTIONS:
                body = normalize_text_block(body, mode="preserve_md_list")
            if not body or not body.strip():
                # 空区块整体跳过，不保留空标题
                continue
            ordered_parts.append(f"{header}\n{body}")
        ctx["assembled_context"] = normalize_text_block(
            "\n\n".join(ordered_parts), mode="preserve_md_list")
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
            # RAG 职责重定位：查询类型白名单强制（正文类 + CSV 创作知识）。
            # 设定类（角色/世界观/力量体系/金手指/卷纲/反派/伏笔）已由 selectable
            # 结构化资源注入提供，LLM 若生成设定类查询在此被过滤，避免重复/死查询。
            allowed = rag_svc.ALLOWED_QUERY_TYPES
            for query, emb in zip(queries, embeddings):
                if not emb:
                    continue
                raw_types = query.get("types") or []
                if not isinstance(raw_types, list):
                    raw_types = [raw_types]
                chunk_types = [t for t in raw_types if t in allowed]
                if not chunk_types:
                    continue  # 查询类型全部不在白名单内，跳过该查询
                # limit 硬上限 8（防注入膨胀），非法 limit 用默认 5
                try:
                    limit = max(1, min(int(query.get("limit", 5)), 8))
                except (TypeError, ValueError):
                    limit = 5
                results = rag_svc.search(
                    project_id, emb,
                    limit=limit,
                    chunk_types=chunk_types,
                )
                for r in results:
                    _r = dict(r)
                    # 章节原文片段：扩展前后各1段上下文（与 RAG 浏览接口一致），
                    # 避免命中段落孤立、叙事被切断，QA 与写作注入共用完整窗口。
                    if _r.get("chunk_type") == "chapter_paragraph":
                        try:
                            meta = _r.get("metadata") or {}
                            if isinstance(meta, str):
                                meta = json.loads(meta) if meta.strip() else {}
                            para_idx = meta.get("para_index")
                            ch_num = _r.get("chapter_number", 0)
                            if para_idx is not None and ch_num:
                                ctx_tuples = rag_svc.get_paragraphs_context(
                                    project_id, ch_num, para_idx, context_range=1)
                                ctx_before = []
                                ctx_after = []
                                for text, idx in ctx_tuples:
                                    if idx < para_idx:
                                        ctx_before.append(text)
                                    elif idx > para_idx:
                                        ctx_after.append(text)
                                _r["context_before"] = "\n".join(ctx_before)
                                _r["context_after"] = "\n".join(ctx_after)
                                segments = []
                                if any(str(x).strip() for x in ctx_before):
                                    segments.append("\n".join(ctx_before))
                                segments.append(_r.get("content", ""))
                                if any(str(x).strip() for x in ctx_after):
                                    segments.append("\n".join(ctx_after))
                                _r["content"] = "\n".join(segments)
                        except Exception:
                            pass
                    from utils.prompt_normalizer import normalize_text_block
                    content = _r.get("content", "")
                    dedup = content[:50] + "|" + content[-50:] if len(content) > 100 else content
                    if dedup not in seen:
                        seen.add(dedup)
                        _r["content"] = normalize_text_block(content)
                        all_results.append(_r)

            return all_results[:10]

        except ContextAnalysisError:
            raise
        except Exception as e:
            raise ContextAnalysisError(f"RAG 查询失败: {e}")

