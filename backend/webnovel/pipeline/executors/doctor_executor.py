"""执行器：项目体检执行器。

参考webnovel-writer的webnovel-doctor SKILL，实现项目体检功能。
"""

import sqlite3
import os
from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from repositories.base_repository import _get_conn


class DoctorExecutor(BaseExecutor):
    """项目体检执行器。"""

    step_name = "doctor_executor"
    step_description = "项目体检"
    step_weight = 5

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行项目体检。"""
        try:
            script_id = self.script_id
            deep_check = context.get("deep", False)

            issues = []
            warnings = []
            checks = []

            conn = _get_conn()

            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'webnovel_%'")
            tables = [row[0] for row in cursor.fetchall()]
            expected_tables = [
                "webnovel_project", "webnovel_golden_finger", "webnovel_character_card",
                "webnovel_character_group", "webnovel_villain", "webnovel_power_system",
                "webnovel_worldview", "webnovel_volume_outline",
                "webnovel_timeline", "webnovel_genre_fusion", "webnovel_state", "webnovel_chapter_meta"
            ]

            for expected in expected_tables:
                if expected in tables:
                    checks.append(f"✓ {expected} 表存在")
                else:
                    issues.append(f"✗ {expected} 表缺失")

            cursor = conn.execute("SELECT * FROM webnovel_project WHERE script_id = ?", (script_id,))
            project = cursor.fetchone()
            if project:
                checks.append(f"✓ 项目记录存在（ID={project[0]}）")
                project_id = project[0]

                checks.append("\n--- 主表数据检查 ---")

                cursor = conn.execute("SELECT COUNT(*) FROM webnovel_character_card WHERE project_id = ?", (project_id,))
                char_count = cursor.fetchone()[0]
                if char_count > 0:
                    checks.append(f"✓ 角色卡 {char_count} 条")
                else:
                    warnings.append(f"⚠ 角色卡为空")

                cursor = conn.execute("SELECT COUNT(*) FROM webnovel_volume_outline WHERE project_id = ?", (project_id,))
                vo_count = cursor.fetchone()[0]
                if vo_count > 0:
                    checks.append(f"✓ 卷纲 {vo_count} 条")
                else:
                    warnings.append(f"⚠ 卷纲为空")

                if deep_check:
                    checks.append("\n--- 深度检查 ---")

                    cursor = conn.execute("SELECT COUNT(*) FROM webnovel_worldview WHERE project_id = ?", (project_id,))
                    wv_count = cursor.fetchone()[0]
                    checks.append(f"世界观设定 {wv_count} 条")

                    cursor = conn.execute("SELECT COUNT(*) FROM webnovel_power_system WHERE project_id = ?", (project_id,))
                    ps_count = cursor.fetchone()[0]
                    checks.append(f"力量体系 {ps_count} 条")

                    cursor = conn.execute("SELECT COUNT(*) FROM webnovel_golden_finger WHERE project_id = ?", (project_id,))
                    gf_count = cursor.fetchone()[0]
                    checks.append(f"金手指 {gf_count} 条")

                    cursor = conn.execute("SELECT COUNT(*) FROM webnovel_villain WHERE project_id = ?", (project_id,))
                    villain_count = cursor.fetchone()[0]
                    checks.append(f"反派设定 {villain_count} 条")

            else:
                issues.append("✗ 项目记录不存在，请先执行深度初始化")

            report = {
                "status": "healthy" if not issues else "warning" if warnings else "critical",
                "script_id": script_id,
                "issues": issues,
                "warnings": warnings,
                "checks": checks,
                "total_issues": len(issues),
                "total_warnings": len(warnings),
                "total_checks": len(checks)
            }

            summary = f"体检完成：{len(issues)}个问题，{len(warnings)}个警告"
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={"doctor_report": report}
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"项目体检执行失败: {str(e)}",
                step_summary="项目体检执行失败"
            )