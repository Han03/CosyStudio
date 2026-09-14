# -*- coding: utf-8 -*-
"""方案 v2 实施（二）：草稿/润色/修订去 JSON 包装 + 动态 max_tokens + 审查精炼 + ctx 500。"""
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

# ══════════ F. draft_generate_prompt.md：去 JSON + 每点字数动态 ══════════
patch("webnovel/prompts/draft_generate_prompt.md",
"  每个剧情点独占一段，每段只写1-3句（40-80字），严禁将多个剧情点塞入同一段;",
"  每个剧情点独占一段，每段不超过{draft_point_max}字（1-3句），严禁将多个剧情点塞入同一段;",
must=False)
patch("webnovel/prompts/draft_generate_prompt.md",
"  段落之间用双换行分隔（JSON 中写作反斜杠n反斜杠n），严禁只用单个换行;",
"  段落之间用空行分隔（一个空行），严禁不用空行;",
must=False)
# （输出格式块已由 _fix_blocks.py 替换为纯文本）

# ══════════ G. draft_generator_executor.py：传 draft_point_max + max_tokens 动态 ══════════
patch("webnovel/pipeline/executors/draft_generator_executor.py",
'''                draft_word_min=int(word_cfg.get("draft_word_min", 1200)),
                draft_word_max=int(word_cfg.get("draft_word_max", 1800)),
            )''',
'''                draft_word_min=int(word_cfg.get("draft_word_min", 1200)),
                draft_word_max=int(word_cfg.get("draft_word_max", 1800)),
                draft_point_max=int(word_cfg.get("draft_point_max", 80)),
            )''')
patch("webnovel/pipeline/executors/draft_generator_executor.py",
'''                max_tokens=max(3500, int(word_cfg.get("draft_word_max", 1800)) * 3),''',
'''                max_tokens=int(word_cfg.get("draft_max_tokens", 3500)),''')

# ══════════ H. draft_polish_prompt.md：去 JSON（输出格式块已由 _fix_blocks.py 替换） ══════════
patch("webnovel/prompts/draft_polish_prompt.md",
"system_prompt: 你是一位资深网文润色师，精通各种题材的小说润色，输出严格的JSON格式",
"system_prompt: 你是一位资深网文润色师，精通各种题材的小说润色")

# ══════════ I. draft_polisher_executor.py：max_tokens 动态 ══════════
patch("webnovel/pipeline/executors/draft_polisher_executor.py",
'''                max_tokens=max(8000, int(word_cfg.get("polish_word_max", 5000)) * 2),''',
'''                max_tokens=int(word_cfg.get("polish_max_tokens", 8000)),''')

# ══════════ J. revise_draft_prompt.md：去 JSON ══════════
patch("webnovel/prompts/revise_draft_prompt.md",
"system_prompt: 你是一位专业的网文编辑，擅长修改草稿，输出严格的JSON格式",
"system_prompt: 你是一位专业的网文编辑，擅长修改草稿")
patch("webnovel/prompts/revise_draft_prompt.md",
'''  【输出格式】
  请严格按照JSON格式输出，只输出JSON，不要包含任何其他内容：
  {{"content": "修改后的完整草稿正文..."}}''',
'''  【输出格式】
  请直接输出修改后的完整草稿正文纯文本，不要包含任何JSON、代码块标记或说明文字。''')

# ══════════ K. review_draft_prompt.md：极简输出 ══════════
patch("webnovel/prompts/review_draft_prompt.md",
"  - 未发现问题时 score 给 9-10 分，issues 为空数组",
"  - 未发现问题时 score 给 9-10 分，issues 为空数组\n"
"  - 只输出上述JSON对象本身，禁止输出分析过程、解释文字或代码块标记；description每条不超过40字，fix_hint每条不超过30字，suggestions不超过60字")

# ══════════ L. draft_reviewer_executor.py：审查/修订 max_tokens 动态 ══════════
patch("webnovel/pipeline/executors/draft_reviewer_executor.py",
'''    async def _review_draft(
        self, draft: str, step_ctx: Dict[str, Any], project_id: int
    ) -> List[Dict[str, Any]]:''',
'''    async def _review_draft(
        self, draft: str, step_ctx: Dict[str, Any], project_id: int,
        word_cfg: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:''')
patch("webnovel/pipeline/executors/draft_reviewer_executor.py",
'''            max_tokens=3000,
            script_id=self.script_id,
            project_id=project_id,
            executor_name="draft_reviewer_score",''',
'''            max_tokens=int((word_cfg or {}).get("review_max_tokens", 800)),
            script_id=self.script_id,
            project_id=project_id,
            executor_name="draft_reviewer_score",''')
patch("webnovel/pipeline/executors/draft_reviewer_executor.py",
'''            max_tokens=max(3000, int(word_cfg.get("draft_word_max", 1800)) * 3),''',
'''            max_tokens=int(word_cfg.get("revise_draft_max_tokens", 3000)),''')

# ══════════ M. context_analyzer.py：max_tokens 900→500 ══════════
patch("webnovel/pipeline/context_analyzer.py",
'''                max_tokens=900,
                script_id=self.script_id,
                project_id=env["project_id"],
                executor_name="context_analyzer",''',
'''                max_tokens=500,
                script_id=self.script_id,
                project_id=env["project_id"],
                executor_name="context_analyzer",''')

print("\nF-M 完成")
