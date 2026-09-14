# -*- coding: utf-8 -*-
"""修复 chapter_plot_reviewer word_cfg 传递。"""
p = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\chapter_plot_reviewer_executor.py"
with open(p, encoding="utf-8") as f:
    t = f.read()

# 1. 签名加 word_cfg
old1 = """    async def _review_plot(
        self, plot_list: list, chapter_index: int,
        step_ctx: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:"""
new1 = """    async def _review_plot(
        self, plot_list: list, chapter_index: int,
        step_ctx: Optional[Dict[str, Any]] = None,
        word_cfg: Dict[str, Any] = None,
    ) -> List[Dict[str, Any]]:"""
if old1 not in t:
    raise SystemExit("签名未找到")
t = t.replace(old1, new1, 1)

# 2. 调用点传 word_cfg
old2 = "review_result = await self._review_plot(current_plot, chapter_index, step_ctx)"
new2 = 'review_result = await self._review_plot(current_plot, chapter_index, step_ctx, context.get("word_config") or {})'
if old2 not in t:
    raise SystemExit("调用点未找到")
t = t.replace(old2, new2, 1)

# 3. max_tokens 改 word_cfg
old3 = 'max_tokens=int((context.get("word_config") or {}).get("review_max_tokens", 800)),'
new3 = 'max_tokens=int((word_cfg or {}).get("review_max_tokens", 800)),'
if old3 not in t:
    raise SystemExit("max_tokens 行未找到")
t = t.replace(old3, new3, 1)

with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(t)
print("[OK] 修复完成")
