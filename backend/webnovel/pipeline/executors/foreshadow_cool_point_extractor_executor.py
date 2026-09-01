"""执行器：伏笔和爽点提取器。

参考webnovel-writer的state_projection_writer和memory schema，
从章节内容中提取伏笔（open_loops）和爽点（cool_points），并保存到数据库。
"""

import json
import re
from typing import Dict, Any, List
from ..base_executor import BaseExecutor, ExecutorResult
from webnovel.repositories import (
    get_webnovel_project_by_script, add_open_loop, add_cool_point,
    get_active_open_loops, update_open_loop_resolved, update_open_loop_urgency,
    get_open_loops_by_project
)


class ForeshadowCoolPointExtractorExecutor(BaseExecutor):
    """伏笔和爽点提取器执行器。"""

    step_name = "foreshadow_cool_point_extractor"
    step_description = "伏笔和爽点提取"
    step_weight = 10

    COOL_POINT_TYPES = [
        "装逼打脸", "扮猪吃虎", "越级反杀", "打脸权威", "反派翻车",
        "甜蜜超预期", "突破", "升级", "寻宝", "奇遇",
        "逆袭", "情感", "解谜", "反转", "发现"
    ]

    FORESHA_DOW_TIERS = ["核心", "支线", "装饰"]

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行伏笔和爽点提取。"""
        try:
            script_id = self.script_id
            chapter_index = self.chapter_index

            polished_content = context.get("polished_content", "") or context.get("draft_content", "")
            
            if not polished_content:
                return ExecutorResult(
                    success=True,
                    step_summary="内容为空，跳过伏笔和爽点提取",
                    output_data={"open_loops": [], "cool_points": []}
                )

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="项目不存在",
                    step_summary="伏笔和爽点提取失败"
                )
            project_id = project["id"]

            open_loops, cool_points = await self._extract_from_content(
                polished_content, chapter_index, project.get("genre", ""), project
            )

            # 跨章去重：与已有伏笔比对，避免重复埋线（如“灰布袋”在前章已埋过）
            open_loops = self._deduplicate_against_existing(open_loops, project_id)

            saved_loops = []
            saved_cool_points = []
            newly_planted_ids = set()

            for loop in open_loops:
                saved = add_open_loop(
                    project_id=project_id,
                    content=loop["content"],
                    tier=loop.get("tier", ""),
                    planted_chapter=chapter_index,
                    target_chapter=loop.get("target_chapter", 0),
                    evidence=loop.get("evidence", "")
                )
                saved_loops.append(saved)
                if saved and saved.get("id"):
                    newly_planted_ids.add(saved["id"])

            for cp in cool_points:
                saved = add_cool_point(
                    project_id=project_id,
                    chapter_number=chapter_index,
                    content=cp["content"],
                    cool_point_type=cp.get("cool_point_type", ""),
                    execution_mode=cp.get("execution_mode", ""),
                    structure_stage=cp.get("structure_stage", ""),
                    pressure_level=cp.get("pressure_level", 0),
                    release_level=cp.get("release_level", 0),
                    reader_emotion=cp.get("reader_emotion", ""),
                    impact_score=cp.get("impact_score", 0),
                    evidence=cp.get("evidence", "")
                )
                saved_cool_points.append(saved)

            await self._check_resolved_loops(project_id, chapter_index, polished_content, exclude_ids=newly_planted_ids)

            update_open_loop_urgency(project_id, chapter_index)

            summary = f"伏笔和爽点提取完成：新增{len(saved_loops)}个伏笔，{len(saved_cool_points)}个爽点"
            
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "open_loops": saved_loops,
                    "cool_points": saved_cool_points,
                    "open_loops_count": len(saved_loops),
                    "cool_points_count": len(saved_cool_points)
                }
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"伏笔和爽点提取失败: {str(e)}",
                step_summary="伏笔和爽点提取失败"
            )

    async def _extract_from_content(self, content: str, chapter_index: int, genre: str, project: dict = None) -> tuple:
        """从章节内容中提取伏笔和爽点。"""
        open_loops = []
        cool_points = []

        open_loops_from_tags = self._extract_from_tags(content)
        open_loops.extend(open_loops_from_tags)

        cool_points_from_tags = self._extract_cool_points_from_tags(content)
        cool_points.extend(cool_points_from_tags)

        from core.model_executor import get_model_executor

        cool_point_types_str = ", ".join(self.COOL_POINT_TYPES)
        foreshadow_tiers_str = ", ".join(self.FORESHA_DOW_TIERS)

        # 从 .md 文件加载 prompt 模板
        prompt_data = self._load_prompt("extract_foreshadow_cool_point")
        prompt = prompt_data["user_prompt"].format(
            content=content[:3000],
            genre=genre,
            cool_point_types=cool_point_types_str,
            foreshadow_tiers=foreshadow_tiers_str,
        )
        system_prompt = prompt_data["system_prompt"] or "你是一位专业的网文分析助手，擅长识别故事中的伏笔和爽点"

        executor = get_model_executor()
        project_id = project["id"] if project else 0
        result = await executor.execute_text_chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=1500,
            script_id=self.script_id,
            project_id=project_id,
            executor_name=self.step_name,
            prompt_name="extract_foreshadow_cool_point",
        )

        response_content = result.get("content", "") if result and "error" not in result else ""

        if not response_content:
            return open_loops, cool_points

        try:
            from utils.llm_json_parser import parse_llm_json
            data = parse_llm_json(
                response_content,
                script_id=self.script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="extract_foreshadow_cool_point",
            )
        except Exception:
            data = {"open_loops": [], "cool_points": []}

        if not data:
            data = {"open_loops": [], "cool_points": []}

        llm_open_loops = data.get("open_loops", [])
        llm_cool_points = data.get("cool_points", [])

        open_loops.extend(llm_open_loops)
        cool_points.extend(llm_cool_points)

        open_loops = self._deduplicate_loops(open_loops)
        cool_points = self._deduplicate_cool_points(cool_points)

        return open_loops, cool_points

    def _extract_from_tags(self, content: str) -> List[Dict]:
        """从内容中的[伏笔: ...]标记提取伏笔。"""
        pattern = r'\[伏笔:\s*(.*?)\]'
        matches = re.findall(pattern, content)
        loops = []
        for match in matches:
            parts = match.strip().split('|')
            content_text = parts[0].strip()
            tier = parts[1].strip() if len(parts) > 1 else "装饰"
            loops.append({
                "content": content_text,
                "tier": tier,
                "target_chapter": 0,
                "evidence": f"[伏笔: {match}]"
            })
        return loops

    def _extract_cool_points_from_tags(self, content: str) -> List[Dict]:
        """从内容中的[爽点: ...]标记提取爽点。"""
        pattern = r'\[爽点:\s*(.*?)\]'
        matches = re.findall(pattern, content)
        cool_points = []
        for match in matches:
            parts = match.strip().split('/')
            cp_type = parts[0].strip() if len(parts) > 0 else ""
            cp_desc = parts[1].strip() if len(parts) > 1 else cp_type
            cool_points.append({
                "content": cp_desc,
                "cool_point_type": cp_type,
                "execution_mode": cp_type,
                "structure_stage": "爆发",
                "pressure_level": 3,
                "release_level": 4,
                "reader_emotion": "爽",
                "impact_score": 7,
                "evidence": f"[爽点: {match}]"
            })
        return cool_points

    def _deduplicate_loops(self, loops: List[Dict]) -> List[Dict]:
        """去重伏笔列表。"""
        seen = set()
        result = []
        for loop in loops:
            key = loop.get("content", "")[:100]
            if key not in seen:
                seen.add(key)
                result.append(loop)
        return result

    def _deduplicate_against_existing(self, loops: List[Dict], project_id: int) -> List[Dict]:
        """跨章去重：与数据库中已有伏笔比对，过滤重复埋线。

        采用关键词包含策略：若新伏笔的核心关键词（前 50 字）已存在于
        任意已有伏笔的 content 中，则视为重复，跳过入库。
        """
        if not loops or not project_id:
            return loops
        try:
            existing = get_open_loops_by_project(project_id)
        except Exception:
            return loops
        if not existing:
            return loops

        existing_contents = [e.get("content", "") for e in existing if e.get("content")]
        result = []
        for loop in loops:
            new_key = loop.get("content", "")[:50]
            if not new_key:
                continue
            # 检查新伏笔关键词是否已被已有伏笔覆盖
            is_dup = any(new_key in ec or ec[:50] in new_key for ec in existing_contents)
            if not is_dup:
                result.append(loop)
        return result

    def _deduplicate_cool_points(self, cool_points: List[Dict]) -> List[Dict]:
        """去重爽点列表。"""
        seen = set()
        result = []
        for cp in cool_points:
            key = cp.get("content", "")[:100]
            if key not in seen:
                seen.add(key)
                result.append(cp)
        return result

    async def _check_resolved_loops(self, project_id: int, chapter_index: int, content: str, exclude_ids: set = None):
        """检查是否有伏笔在本章被回收。

        exclude_ids: 本章新埋的伏笔 ID 集合，这些伏笔不可能在本章被回收，
        必须排除以避免“同章埋设+回收”的矛盾。
        """
        active_loops = get_active_open_loops(project_id)
        if not active_loops:
            return

        # 排除本章刚埋下的伏笔（它们不可能在同一章被回收）
        if exclude_ids:
            active_loops = [lp for lp in active_loops if lp.get("id") not in exclude_ids]
            if not active_loops:
                return

        from core.model_executor import get_model_executor

        loops_text = "\n".join([
            f"- [{loop['tier']}] {loop['content']} (第{loop['planted_chapter']}章埋下)"
            for loop in active_loops
        ])

        # 从 .md 文件加载 prompt 模板
        prompt_data = self._load_prompt("check_resolved_loops")
        prompt = prompt_data["user_prompt"].format(
            loops_text=loops_text,
            content=content[:2000],
        )
        system_prompt = prompt_data["system_prompt"] or "你是一位专业的故事分析助手，擅长识别伏笔的回收"

        executor = get_model_executor()
        result = await executor.execute_text_chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=500,
            script_id=self.script_id,
            project_id=project_id,
            executor_name=self.step_name,
            prompt_name="check_resolved_loops",
        )

        response_content = result.get("content", "") if result else ""

        try:
            from utils.llm_json_parser import parse_llm_json
            data = parse_llm_json(
                response_content,
                script_id=self.script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="check_resolved_loops",
            )
            resolved_indices = data.get("resolved_indices", [])
            
            for idx in resolved_indices:
                if 0 <= idx < len(active_loops):
                    loop_id = active_loops[idx]["id"]
                    update_open_loop_resolved(loop_id, chapter_index)
        except Exception:
            pass
