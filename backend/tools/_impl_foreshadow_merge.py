# -*- coding: utf-8 -*-
"""伏笔处理合并实施：
1. 新建 foreshadow_processor_prompt.md（新埋+回收一次判断），删除 check_resolved_loops_prompt.md
2. fact_record_prompt.md 删除 open_loops 块（7→6 块）
3. fact_recorder_executor.py：
   - _parse_all 7→6 块
   - _save_foreshadow_and_cool_point → _save_cool_points（仅爽点）
   - 新增 _process_foreshadows（新埋提取落库 + 回收判断，一次 LLM）
   - 删除 _check_resolved_loops
   - 主流程/摘要/输出调整
"""
import py_compile, os

PROMPTS = r"C:\MyProjects\CosyStudio\backend\webnovel\prompts"
EXEC = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\fact_recorder_executor.py"

# ── 1. 新 prompt：foreshadow_processor_prompt.md ──
new_prompt = '''---
system_prompt: 你是一位专业的故事分析助手，擅长识别伏笔的埋设与回收，输出严格的JSON格式
user_prompt: |
  请对本章内容做伏笔分析：识别【本章新埋下的伏笔】与【活跃伏笔列表中被回收的伏笔】。

  【本章内容】
  {chapter_content}

  【活跃伏笔列表】
  {active_loops}

  判断规则：
  1. 新埋伏笔：本章正文中**新出现**、尚未解决的线索（物品、设定、事件、人物疑点等），且不在活跃伏笔列表中。
     已在列表中的伏笔不得作为新埋伏笔提取；前面章节已交代过的物品、设定或事件也不得作为新伏笔。
  2. 回收判断：列表中某伏笔在本章被明确回收、揭示、兑现或解决时，输出其编号（对应【活跃伏笔列表】中的序号）。
     若某情节只是被提及、被推进，但未解决，不算回收。
  3. 同一伏笔不得既算新埋又算回收：列表中的伏笔若在本章被解决，只计入回收；新出现的未解决线索，只计入新埋。

  输出JSON格式（只输出JSON）：
  {{
    "open_loops": [
      {{"content": "伏笔内容描述", "tier": "核心/支线/装饰", "target_chapter": 0, "evidence": "原文证据片段"}}
    ],
    "resolved_indices": [0, 2, 5]
  }}
  - tier：核心伏笔回收周期50-300章，支线30-100章，装饰10-30章；target_chapter：预计回收章节（0表示未定）
  - open_loops 无内容时输出空数组；resolved_indices 无回收时输出空数组。
---
'''
with open(os.path.join(PROMPTS, "foreshadow_processor_prompt.md"), "w", encoding="utf-8", newline="\n") as f:
    f.write(new_prompt)
os.remove(os.path.join(PROMPTS, "check_resolved_loops_prompt.md"))
print("[OK] 新建 foreshadow_processor_prompt.md，删除 check_resolved_loops_prompt.md")

# ── 2. fact_record_prompt.md 删 open_loops 块 ──
p = os.path.join(PROMPTS, "fact_record_prompt.md")
t = open(p, encoding="utf-8").read()
old_block = '''  【伏笔 open_loops】本章新埋下的伏笔（不要提取已在前面章节交代过的物品、设定或事件作为新伏笔）：
  - content: 伏笔内容描述
  - tier: 核心/支线/装饰（核心伏笔回收周期50-300章，支线30-100章，装饰10-30章）
  - target_chapter: 预计回收章节（0表示未定）
  - evidence: 原文证据片段

'''
assert old_block in t, "open_loops 块未找到"
t = t.replace(old_block, "", 1)
old_fmt = '"open_loops": [{{"content": "伏笔内容", "tier": "核心/支线/装饰", "target_chapter": 0, "evidence": "证据"}}], '
assert old_fmt in t, "输出格式 open_loops 未找到"
t = t.replace(old_fmt, "", 1)
old_line = "  open_loops/cool_points/character_states/item_changes/character_updates/world_settings 无内容时输出空数组，hook 无内容时输出空对象。"
new_line = "  cool_points/character_states/item_changes/character_updates/world_settings 无内容时输出空数组，hook 无内容时输出空对象。"
assert old_line in t
t = t.replace(old_line, new_line, 1)
with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(t)
print("[OK] fact_record_prompt.md 已删除 open_loops 块")

# ── 3. fact_recorder_executor.py ──
src = open(EXEC, encoding="utf-8").read()

# 3.1 _parse_all 7→6 块
old = '''    def _parse_all(self, content: str, script_id: int, project_id: int):
        """解析七块提取结果：item_changes / character_updates / open_loops / cool_points / hook / character_states / world_settings（容错）。"""
        item_changes, character_updates, open_loops, cool_points, hook, character_states, world_settings = [], [], [], [], {}, [], []
        if not content:
            return item_changes, character_updates, open_loops, cool_points, hook, character_states, world_settings

        fact_data = parse_llm_json(
            content,
            script_id=script_id,
            project_id=project_id,
            executor_name=self.step_name,
            prompt_name="fact_record",
        )
        if fact_data and isinstance(fact_data, dict):
            item_changes = [i for i in (fact_data.get("item_changes") or [])
                           if isinstance(i, dict) and i.get("character") and i.get("item")]
            character_updates = [u for u in (fact_data.get("character_updates") or [])
                                if isinstance(u, dict) and u.get("type")]
            open_loops = [l for l in (fact_data.get("open_loops") or [])
                          if isinstance(l, dict) and l.get("content")]
            cool_points = [c for c in (fact_data.get("cool_points") or [])
                           if isinstance(c, dict) and c.get("content")]
            hook = fact_data.get("hook") or {}
            if not isinstance(hook, dict):
                hook = {}
            character_states = [s for s in (fact_data.get("character_states") or [])
                                if isinstance(s, dict) and s.get("character_id")]
            world_settings = [w for w in (fact_data.get("world_settings") or [])
                              if isinstance(w, dict) and w.get("name") and w.get("content")]
        # JSON 解析失败或缺失：全部结构化块为空（无文本兜底）
        return item_changes, character_updates, open_loops, cool_points, hook, character_states, world_settings'''
new = '''    def _parse_all(self, content: str, script_id: int, project_id: int):
        """解析六块提取结果：item_changes / character_updates / cool_points / hook / character_states / world_settings（容错）。"""
        item_changes, character_updates, cool_points, hook, character_states, world_settings = [], [], [], {}, [], []
        if not content:
            return item_changes, character_updates, cool_points, hook, character_states, world_settings

        fact_data = parse_llm_json(
            content,
            script_id=script_id,
            project_id=project_id,
            executor_name=self.step_name,
            prompt_name="fact_record",
        )
        if fact_data and isinstance(fact_data, dict):
            item_changes = [i for i in (fact_data.get("item_changes") or [])
                           if isinstance(i, dict) and i.get("character") and i.get("item")]
            character_updates = [u for u in (fact_data.get("character_updates") or [])
                                if isinstance(u, dict) and u.get("type")]
            cool_points = [c for c in (fact_data.get("cool_points") or [])
                           if isinstance(c, dict) and c.get("content")]
            hook = fact_data.get("hook") or {}
            if not isinstance(hook, dict):
                hook = {}
            character_states = [s for s in (fact_data.get("character_states") or [])
                                if isinstance(s, dict) and s.get("character_id")]
            world_settings = [w for w in (fact_data.get("world_settings") or [])
                              if isinstance(w, dict) and w.get("name") and w.get("content")]
        # JSON 解析失败或缺失：全部结构化块为空（无文本兜底）
        return item_changes, character_updates, cool_points, hook, character_states, world_settings'''
assert old in src, "_parse_all 未匹配"
src = src.replace(old, new, 1)

# 3.2 主流程解析与落库
old = '''            content = result.get("content", "") if result else ""
            (item_changes, character_updates, open_loops, cool_points, hook,
             character_states, world_settings) = self._parse_all(
                content, script_id, project_id)'''
new = '''            content = result.get("content", "") if result else ""
            (item_changes, character_updates, cool_points, hook,
             character_states, world_settings) = self._parse_all(
                content, script_id, project_id)'''
assert old in src, "主流程解析未匹配"
src = src.replace(old, new, 1)

old = '''            # 2. 伏笔爽点落库（含标签补充+跨章去重）+ 3. 结尾钩子 + 4. 角色状态 + 5. 伏笔回收检查
            newly_planted_ids = set()
            if project_id:
                newly_planted_ids = await self._save_foreshadow_and_cool_point(
                    project_id, self.chapter_index, open_loops, cool_points, polished_content)
                await self._save_hook(project_id, self.chapter_index, hook)
                await self._save_character_states(project_id, self.chapter_index, character_states)
                await self._save_world_settings(project_id, self.chapter_index, world_settings)
                await self._check_resolved_loops(
                    project_id, self.chapter_index, polished_content, exclude_ids=newly_planted_ids)'''
new = '''            # 2. 爽点落库（含标签补充+去重）+ 3. 结尾钩子 + 4. 角色状态 + 5. 伏笔处理（新埋+回收，一次 LLM）
            planted_loop_count = 0
            if project_id:
                await self._save_cool_points(project_id, self.chapter_index, cool_points, polished_content)
                await self._save_hook(project_id, self.chapter_index, hook)
                await self._save_character_states(project_id, self.chapter_index, character_states)
                await self._save_world_settings(project_id, self.chapter_index, world_settings)
                planted_loop_count = await self._process_foreshadows(
                    project_id, self.chapter_index, polished_content)'''
assert old in src, "落库段未匹配"
src = src.replace(old, new, 1)

# 3.3 摘要与输出
old = '''            summary = (f"事实记录完成：{len(open_loops)}个伏笔，"
                       f"{len(cool_points)}个爽点，{len(character_states)}条角色状态"
                       f"{item_tail}{char_tail}"
                       + (f"，{len(world_settings)}条设定" if world_settings else ""))'''
new = '''            summary = (f"事实记录完成：{planted_loop_count}个伏笔，"
                       f"{len(cool_points)}个爽点，{len(character_states)}条角色状态"
                       f"{item_tail}{char_tail}"
                       + (f"，{len(world_settings)}条设定" if world_settings else ""))'''
assert old in src, "摘要未匹配"
src = src.replace(old, new, 1)

old = '''                    "open_loops_count": len(open_loops),'''
new = '''                    "open_loops_count": planted_loop_count,'''
assert old in src, "输出 open_loops_count 未匹配"
src = src.replace(old, new, 1)

# 3.4 _save_foreshadow_and_cool_point → _save_cool_points
old = '''    async def _save_foreshadow_and_cool_point(
        self, project_id: int, chapter_index: int,
        open_loops: List[Dict], cool_points: List[Dict], content: str
    ) -> set:
        """落库伏笔与爽点（含标签补充、跨章去重），返回本章新埋伏笔 id 集合。"""
        open_loops = list(open_loops) + self._extract_from_tags(content)
        cool_points = list(cool_points) + self._extract_cool_points_from_tags(content)
        open_loops = self._deduplicate_loops(open_loops)
        cool_points = self._deduplicate_cool_points(cool_points)
        open_loops = self._deduplicate_against_existing(open_loops, project_id)

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
            if saved and saved.get("id"):
                newly_planted_ids.add(saved["id"])

        for cp in cool_points:'''
new = '''    async def _save_cool_points(
        self, project_id: int, chapter_index: int,
        cool_points: List[Dict], content: str
    ) -> None:
        """落库爽点（含标签补充、去重）。"""
        cool_points = list(cool_points) + self._extract_cool_points_from_tags(content)
        cool_points = self._deduplicate_cool_points(cool_points)

        for cp in cool_points:'''
assert old in src, "_save_foreshadow_and_cool_point 未匹配"
src = src.replace(old, new, 1)

old = '''        update_open_loop_urgency(project_id, chapter_index)
        return newly_planted_ids

    async def _save_hook'''
new = '''        update_open_loop_urgency(project_id, chapter_index)

    async def _save_hook'''
assert old in src, "urgency 段未匹配"
src = src.replace(old, new, 1)

# 3.5 新增 _process_foreshadows，删除 _check_resolved_loops
old = '''    async def _check_resolved_loops(
        self, project_id: int, chapter_index: int, content: str, exclude_ids: set = None
    ):
        """检查是否有伏笔在本章被回收。

        exclude_ids: 本章新埋的伏笔 ID 集合，这些伏笔不可能在本章被回收，
        必须排除以避免"同章埋设+回收"的矛盾。
        """
        active_loops = get_active_open_loops(project_id)
        if not active_loops:
            return
        if exclude_ids:
            active_loops = [lp for lp in active_loops if lp.get("id") not in exclude_ids]
            if not active_loops:
                return

        from core.model_executor import get_model_executor

        loops_text = "\\n".join([
            f"- [{loop['tier']}] {loop['content']} (第{loop['planted_chapter']}章埋下)"
            for loop in active_loops
        ])

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
            pass'''
new = '''    async def _process_foreshadows(
        self, project_id: int, chapter_index: int, content: str
    ) -> int:
        """伏笔处理：识别并落库本章新埋伏笔 + 判断活跃伏笔回收（一次 LLM 调用）。

        新埋伏笔提取与回收判断在同一上下文完成，清单中已有伏笔不会被重复提取，
        天然避免"同章埋设+回收"矛盾，无需 exclude_ids 排除。
        """
        active_loops = get_active_open_loops(project_id) or []
        loops_text = "\\n".join([
            f"[{i}] [{loop.get('tier', '')}] {loop.get('content', '')} "
            f"(第{loop.get('planted_chapter', 0)}章埋下)"
            for i, loop in enumerate(active_loops)
        ]) if active_loops else "（无活跃伏笔）"

        from core.model_executor import get_model_executor

        prompt_data = self._load_prompt("foreshadow_processor")
        prompt = prompt_data["user_prompt"].format(
            chapter_content=content[:3500],
            active_loops=loops_text,
        )
        system_prompt = prompt_data["system_prompt"] or (
            "你是一位专业的故事分析助手，擅长识别伏笔的埋设与回收")

        executor = get_model_executor()
        result = await executor.execute_text_chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=1200,
            script_id=self.script_id,
            project_id=project_id,
            executor_name=self.step_name,
            prompt_name="foreshadow_processor",
        )
        response_content = result.get("content", "") if result else ""
        data = {}
        try:
            data = parse_llm_json(
                response_content,
                script_id=self.script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="foreshadow_processor",
            ) or {}
        except Exception:
            data = {}

        # 新埋伏笔：LLM 提取 + 正文标记补充 → 本章去重 → 跨章去重 → 落库
        open_loops = [l for l in (data.get("open_loops") or [])
                      if isinstance(l, dict) and l.get("content")]
        open_loops += self._extract_from_tags(content)
        open_loops = self._deduplicate_loops(open_loops)
        open_loops = self._deduplicate_against_existing(open_loops, project_id)
        planted_count = 0
        for loop in open_loops:
            saved = add_open_loop(
                project_id=project_id,
                content=loop["content"],
                tier=loop.get("tier", ""),
                planted_chapter=chapter_index,
                target_chapter=loop.get("target_chapter", 0),
                evidence=loop.get("evidence", "")
            )
            if saved and saved.get("id"):
                planted_count += 1

        # 回收判断：更新被回收伏笔状态
        resolved_indices = data.get("resolved_indices") or []
        for idx in resolved_indices:
            if isinstance(idx, int) and 0 <= idx < len(active_loops):
                update_open_loop_resolved(active_loops[idx]["id"], chapter_index)

        update_open_loop_urgency(project_id, chapter_index)
        return planted_count'''
assert old in src, "_check_resolved_loops 未匹配"
src = src.replace(old, new, 1)

with open(EXEC, "w", encoding="utf-8", newline="\n") as f:
    f.write(src)
py_compile.compile(EXEC, doraise=True)
print("[OK] fact_recorder_executor.py 已更新")
