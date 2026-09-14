# -*- coding: utf-8 -*-
"""方案 v2 实施：目标字数驱动的全节点动态参数 + 去 JSON 包装 + 审查/分析精炼。"""
import os

BACKEND = r"C:\MyProjects\CosyStudio\backend"

def patch(path, old, new, must=True):
    p = os.path.join(BACKEND, path)
    with open(p, encoding="utf-8") as f:
        text = f.read()
    if old not in text:
        if must:
            raise SystemExit(f"[FAIL] 未找到: {path}\n---\n{old[:200]}")
        return False
    text = text.replace(old, new, 1)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"[OK] {path}")
    return True

# ══════════ A. orchestrator.py：word_config 全参数矩阵 ══════════
patch("webnovel/pipeline/orchestrator.py",
'''        raw = int(self._context.get("chapter_words", 0) or 0)
        if raw <= 0:
            raw = 4000
        polish_min = round(raw * 0.8)
        polish_max = round(raw * 1.2)
        # 草稿为白描骨架，约为成品的 40%-60%（0.4→0.5：草稿过短导致润色扩写不达标）
        draft_min = round(polish_min * 0.5)
        draft_max = round(polish_max * 0.5)
        self._context["word_config"] = {
            "chapter_words": raw,
            "polish_word_min": polish_min,
            "polish_word_max": polish_max,
            "draft_word_min": draft_min,
            "draft_word_max": draft_max,
        }''',
'''        raw = int(self._context.get("chapter_words", 0) or 0)
        if raw <= 0:
            raw = 4000
        polish_min = round(raw * 0.8)
        polish_max = round(raw * 1.2)
        # 草稿为白描骨架，约为成品的 40%-60%（0.4→0.5：草稿过短导致润色扩写不达标）
        draft_min = round(polish_min * 0.5)
        draft_max = round(polish_max * 0.5)
        # 剧情点数量：每点成品约 250 字，clamp 4-10；每点描述上限固定 60 字
        plot_count = max(4, min(10, round(raw / 250)))
        plot_desc_max = 60
        # 每点草稿上限：草稿总量 / 剧情点数（不低于 60 字）
        draft_point_max = max(60, draft_max // max(plot_count, 1))
        # max_tokens：中文 1 字 ≈ 1.5-2 tok，按上限 ×2 留余量
        self._context["word_config"] = {
            "chapter_words": raw,
            "polish_word_min": polish_min,
            "polish_word_max": polish_max,
            "draft_word_min": draft_min,
            "draft_word_max": draft_max,
            "plot_count": plot_count,
            "plot_desc_max": plot_desc_max,
            "draft_point_max": draft_point_max,
            "polish_max_tokens": max(1500, polish_max * 2),
            "draft_max_tokens": max(800, draft_max * 2),
            "revise_draft_max_tokens": max(800, draft_max * 2),
            "plot_max_tokens": max(1200, plot_count * 400),
            "plot_revise_max_tokens": max(1200, plot_count * 400),
            "review_max_tokens": 800,
        }''')

# ══════════ B. chapter_plot_generate_prompt.md：动态数量/描述上限 ══════════
patch("webnovel/prompts/chapter_plot_generate_prompt.md",
'''        "scene": "场景简述（20-40字）",
        "description": "详细剧情描述（50-100字，包含具体事件、角色行为、情绪变化）",''',
'''        "scene": "场景简述（20字以内）",
        "description": "详细剧情描述（{plot_desc_max}字以内，只写具体事件与角色行为，不写环境铺陈与心理描写）",''')
patch("webnovel/prompts/chapter_plot_generate_prompt.md",
"  注意：plots数组应包含8-12个剧情点，按时间顺序排列，覆盖装配上下文【章节规划】中的所有关键事件和必须覆盖节点。",
"  注意：plots数组应包含{plot_count}个剧情点（不要多也不要少），按时间顺序排列，覆盖装配上下文【章节规划】中的所有关键事件和必须覆盖节点。")

# ══════════ C. chapter_plot_generator_executor.py：动态参数 ══════════
patch("webnovel/pipeline/executors/chapter_plot_generator_executor.py",
'''            # 加载 prompt 模板并填充
            prompt_data = self._load_prompt("chapter_plot_generate")
            full_prompt = prompt_data["user_prompt"].format(
                chapter_index=chapter_index,
                continue_prev=continue_prev,
                assembled_context=step_ctx["assembled_context"],
            )''',
'''            # 加载 prompt 模板并填充
            prompt_data = self._load_prompt("chapter_plot_generate")
            word_cfg = context.get("word_config") or {}
            full_prompt = prompt_data["user_prompt"].format(
                chapter_index=chapter_index,
                continue_prev=continue_prev,
                assembled_context=step_ctx["assembled_context"],
                plot_count=int(word_cfg.get("plot_count", 8)),
                plot_desc_max=int(word_cfg.get("plot_desc_max", 60)),
            )''')
patch("webnovel/pipeline/executors/chapter_plot_generator_executor.py",
'''                max_tokens=3000,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name=f"chapter_plot_{chapter_index}",''',
'''                max_tokens=int((context.get("word_config") or {}).get("plot_max_tokens", 3000)),
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name=f"chapter_plot_{chapter_index}",''')

# ══════════ D. chapter_plot_review_prompt.md：极简输出 ══════════
patch("webnovel/prompts/chapter_plot_review_prompt.md",
"  - overall_passed：当且仅当所有维度不存在worth_revising=true的问题、且不存在suggestions_actionable=true的建议时，才为true。",
"  - overall_passed：当且仅当所有维度不存在worth_revising=true的问题、且不存在suggestions_actionable=true的建议时，才为true。\n"
"  - 只输出上述JSON对象本身，禁止输出分析过程、解释文字或代码块标记；description每条不超过40字，fix_hint每条不超过30字，suggestions不超过60字。")

# ══════════ E. chapter_plot_reviewer_executor.py：审查/修订 max_tokens 动态 ══════════
patch("webnovel/pipeline/executors/chapter_plot_reviewer_executor.py",
'''                # 触发修正
                revised_plot = await self._revise_plot(current_plot, review_result)''',
'''                # 触发修正
                revised_plot = await self._revise_plot(
                    current_plot, review_result, context.get("word_config") or {})''')
patch("webnovel/pipeline/executors/chapter_plot_reviewer_executor.py",
'''    async def _revise_plot(
        self, plot_list: list, review_result: List[Dict[str, Any]]
    ) -> list:''',
'''    async def _revise_plot(
        self, plot_list: list, review_result: List[Dict[str, Any]], word_cfg: Dict[str, Any] = None
    ) -> list:''')
patch("webnovel/pipeline/executors/chapter_plot_reviewer_executor.py",
'''            max_tokens=2000,
            script_id=self.script_id,
            project_id=project_id,
            executor_name="chapter_plot_reviewer_score",''',
'''            max_tokens=int((context.get("word_config") or {}).get("review_max_tokens", 800)),
            script_id=self.script_id,
            project_id=project_id,
            executor_name="chapter_plot_reviewer_score",''')
patch("webnovel/pipeline/executors/chapter_plot_reviewer_executor.py",
'''        result = await executor.execute_text_chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=2500,''',
'''        result = await executor.execute_text_chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=int((word_cfg or {}).get("plot_revise_max_tokens", 2500)),''')

print("\nA-E 完成")
