# -*- coding: utf-8 -*-
"""插入 _save_world_settings 方法到 fact_recorder_executor.py。"""
import os

p = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\fact_recorder_executor.py"
with open(p, encoding="utf-8") as f:
    text = f.read()

METHOD = '''    async def _save_world_settings(
        self, project_id: int, chapter_index: int, world_settings: List[Dict]
    ) -> int:
        """落库本章新交代的世界观设定（追加到 webnovel_worldview.world_summary）。

        无世界观时新建；有则按章分区追加（world_summary 上限 20000 字截断）。
        返回新增条目数。单条失败不阻断。
        """
        count = 0
        try:
            from utils.logger import log_manager
            logger = log_manager.get_logger("fact_recorder")

            if not project_id or not world_settings:
                return 0

            existing = get_worldview_by_project(project_id)
            existing_summary = (existing or {}).get("world_summary", "") or ""

            for ws in world_settings:
                try:
                    name = str(ws.get("name", "") or "").strip()
                    content = str(ws.get("content", "") or "").strip()
                    category = str(ws.get("category", "") or "").strip()
                    if not name or not content or len(name) > 40 or len(content) > 600:
                        continue
                    # 简单查重：名称或内容前缀已存在于世界观则不重复追加
                    if name in existing_summary or content[:30] in existing_summary:
                        continue
                    line = f"【第{chapter_index}章·{category or '其他'}】{name}：{content}"
                    if len(existing_summary) + len(line) > 20000:
                        logger.warning(f"[fact_recorder] 世界观 world_summary 接近上限，跳过: {name}")
                        continue
                    existing_summary = (existing_summary + "\\n\\n" + line).strip()
                    count += 1
                except Exception:
                    continue

            if count == 0:
                return 0
            if existing:
                update_worldview(existing["id"], world_summary=existing_summary)
            else:
                add_worldview(project_id=project_id, world_summary=existing_summary)
            logger.info(f"[fact_recorder] 世界观设定追加完成：{count} 条（第{chapter_index}章）")
        except Exception:
            pass
        return count

'''

ANCHOR = "    async def _check_resolved_loops("
if ANCHOR not in text:
    raise SystemExit("锚点未找到")
text = text.replace(ANCHOR, METHOD + ANCHOR, 1)
with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)
print("[OK] _save_world_settings 已插入")
