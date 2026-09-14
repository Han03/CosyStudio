# -*- coding: utf-8 -*-
"""方案A实施：设定提取并入 fact_recorder，删除 setting_recorder 节点。"""
import os

BACKEND = r"C:\MyProjects\CosyStudio\backend"

def patch(path, old, new, must=True):
    p = os.path.join(BACKEND, path)
    with open(p, encoding="utf-8") as f:  # universal newline → \n
        text = f.read()
    if old not in text:
        if must:
            raise SystemExit(f"[FAIL] 未找到目标文本: {path}\n---\n{old[:200]}")
        return False
    text = text.replace(old, new, 1)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"[OK] {path}")
    return True

# ── 1. fact_recorder_executor.py ──
patch("webnovel/pipeline/executors/fact_recorder_executor.py",
      "    get_chapter_meta, update_chapter_meta, upsert_character_state,\n)",
      "    get_chapter_meta, update_chapter_meta, upsert_character_state,\n"
      "    get_worldview_by_project, add_worldview, update_worldview,\n)")

patch("webnovel/pipeline/executors/fact_recorder_executor.py",
      '    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:\n'
      '        """执行事实记录（归口：事实/伏笔爽点/结尾钩子/角色状态 一次提取 + 回收检查 + 新角色建卡）。"""',
      '    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:\n'
      '        """执行事实记录（归口：事实/伏笔爽点/结尾钩子/角色状态/世界观设定 一次提取 + 回收检查 + 新角色建卡）。"""')

# 解析返回值 6→7 元组
patch("webnovel/pipeline/executors/fact_recorder_executor.py",
      '            item_changes, character_updates, open_loops, cool_points, hook, character_states = self._parse_all(\n'
      '                content, script_id, project_id)',
      '            (item_changes, character_updates, open_loops, cool_points, hook,\n'
      '             character_states, world_settings) = self._parse_all(\n'
      '                content, script_id, project_id)')

# 落库：在角色状态落库后追加设定落库
patch("webnovel/pipeline/executors/fact_recorder_executor.py",
      '                await self._save_character_states(project_id, self.chapter_index, character_states)',
      '                await self._save_character_states(project_id, self.chapter_index, character_states)\n'
      '                await self._save_world_settings(project_id, self.chapter_index, world_settings)')

# summary 增加设定计数
patch("webnovel/pipeline/executors/fact_recorder_executor.py",
      '            summary = (f"事实记录完成：{len(open_loops)}个伏笔，"\n'
      '                       f"{len(cool_points)}个爽点，{len(character_states)}条角色状态"\n'
      '                       f"{item_tail}{char_tail}")',
      '            summary = (f"事实记录完成：{len(open_loops)}个伏笔，"\n'
      '                       f"{len(cool_points)}个爽点，{len(character_states)}条角色状态"\n'
      '                       f"{item_tail}{char_tail}"\n'
      '                       + (f"，{len(world_settings)}条设定" if world_settings else ""))')

# output_data 增加设定计数
patch("webnovel/pipeline/executors/fact_recorder_executor.py",
      '                    "character_states_count": len(character_states),\n'
      '                }',
      '                    "character_states_count": len(character_states),\n'
      '                    "world_settings_count": len(world_settings),\n'
      '                }')

# _parse_all 签名与返回
patch("webnovel/pipeline/executors/fact_recorder_executor.py",
      '    def _parse_all(self, content: str, script_id: int, project_id: int):\n'
      '        """解析六块提取结果：item_changes / character_updates / open_loops / cool_points / hook / character_states（容错）。"""\n'
      '        item_changes, character_updates, open_loops, cool_points, hook, character_states = [], [], [], [], {}, []\n'
      '        if not content:\n'
      '            return item_changes, character_updates, open_loops, cool_points, hook, character_states',
      '    def _parse_all(self, content: str, script_id: int, project_id: int):\n'
      '        """解析七块提取结果：item_changes / character_updates / open_loops / cool_points / hook / character_states / world_settings（容错）。"""\n'
      '        item_changes, character_updates, open_loops, cool_points, hook, character_states, world_settings = [], [], [], [], {}, [], []\n'
      '        if not content:\n'
      '            return item_changes, character_updates, open_loops, cool_points, hook, character_states, world_settings')

patch("webnovel/pipeline/executors/fact_recorder_executor.py",
      '            character_states = [s for s in (fact_data.get("character_states") or [])\n'
      '                                if isinstance(s, dict) and s.get("character_id")]\n'
      '        # JSON 解析失败或缺失：全部结构化块为空（无文本兜底）\n'
      '        return item_changes, character_updates, open_loops, cool_points, hook, character_states',
      '            character_states = [s for s in (fact_data.get("character_states") or [])\n'
      '                                if isinstance(s, dict) and s.get("character_id")]\n'
      '            world_settings = [w for w in (fact_data.get("world_settings") or [])\n'
      '                              if isinstance(w, dict) and w.get("name") and w.get("content")]\n'
      '        # JSON 解析失败或缺失：全部结构化块为空（无文本兜底）\n'
      '        return item_changes, character_updates, open_loops, cool_points, hook, character_states, world_settings')

print("\nfact_recorder_executor.py 修改完成")
