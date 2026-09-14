# -*- coding: utf-8 -*-
"""归一化接入：
1. BaseExecutor 加 _format_prompt（format + normalize）
2. 7 处 write 流程 format 替换为 _format_prompt
3. context_analyzer：RAG 结果 content 归一化 / _assemble_context 区块归一化 / _build_analysis_prompt 归一化
"""
import py_compile

# ── 1. BaseExecutor._format_prompt ──
p_base = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\base_executor.py"
with open(p_base, encoding="utf-8") as f:
    t = f.read()
old = '''    def _load_prompt(self, prompt_name: str) -> Dict[str, str]:'''
new = '''    def _format_prompt(self, template: str, **kwargs) -> str:
        """格式化 prompt 模板并归一化注入内容（去行尾空白/连续空行/全角空格/零宽字符）。"""
        from utils.prompt_normalizer import normalize_text_block
        return normalize_text_block(template.format(**kwargs))

    def _load_prompt(self, prompt_name: str) -> Dict[str, str]:'''
if old not in t:
    raise SystemExit("base_executor 未找到")
t = t.replace(old, new, 1)
with open(p_base, "w", encoding="utf-8", newline="\n") as f:
    f.write(t)
py_compile.compile(p_base, doraise=True)
print("[OK] base_executor._format_prompt")

# ── 2. 7 处 format 替换 ──
executors = [
    # (path, 定位上下文, 替换)
    (r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\chapter_plot_generator_executor.py",
     "full_prompt = prompt_data[\"user_prompt\"].format(",
     "full_prompt = self._format_prompt(prompt_data[\"user_prompt\"], "),
    (r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\chapter_plot_reviewer_executor.py",
     "prompt = prompt_data[\"user_prompt\"].format(",
     "prompt = self._format_prompt(prompt_data[\"user_prompt\"], "),
    (r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\draft_generator_executor.py",
     "full_prompt = prompt_data[\"user_prompt\"].format(",
     "full_prompt = self._format_prompt(prompt_data[\"user_prompt\"], "),
    (r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\draft_polisher_executor.py",
     "full_prompt = prompt_data[\"user_prompt\"].format(",
     "full_prompt = self._format_prompt(prompt_data[\"user_prompt\"], "),
    (r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\draft_reviewer_executor.py",
     "prompt = prompt_data[\"user_prompt\"].format(",
     "prompt = self._format_prompt(prompt_data[\"user_prompt\"], "),
]
for path, old, new in executors:
    with open(path, encoding="utf-8") as f:
        t = f.read()
    if old not in t:
        print(f"[SKIP] {path.split(chr(92))[-1]}: 未找到")
        continue
    t = t.replace(old, new, 1)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(t)
    py_compile.compile(path, doraise=True)
    print(f"[OK] {path.split(chr(92))[-1]}")

# ── 3. context_analyzer ──
p_ctx = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\context_analyzer.py"
with open(p_ctx, encoding="utf-8") as f:
    ct = f.read()

# 3a. RAG 结果 content 归一化
old_rag = '''                for r in results:
                    content = r.get("content", "")
                    dedup = content[:50] + "|" + content[-50:] if len(content) > 100 else content
                    if dedup not in seen:
                        seen.add(dedup)
                        all_results.append(r)'''
new_rag = '''                for r in results:
                    from utils.prompt_normalizer import normalize_text_block
                    content = r.get("content", "")
                    dedup = content[:50] + "|" + content[-50:] if len(content) > 100 else content
                    if dedup not in seen:
                        seen.add(dedup)
                        _r = dict(r)
                        _r["content"] = normalize_text_block(content)
                        all_results.append(_r)'''
if old_rag not in ct:
    raise SystemExit("RAG 归一化点未找到")
ct = ct.replace(old_rag, new_rag, 1)
print("[OK] context_analyzer: RAG 结果归一化")

# 3b. _assemble_context 区块归一化（JSON 块 preserve_json）
old_as = '''        # 7. 按节点区块顺序组装 assembled_context
        ordered = []
        for sec_name, _ in assembly["sections"]:
            if sec_name in sections:
                header = RESOURCE_REGISTRY[sec_name]["header"]
                ordered.append(f"{header}\\n{sections[sec_name]}")
        ctx["assembled_context"] = "\\n\\n".join(ordered)
        ctx["sections"] = sections
        return ctx'''
new_as = '''        # 7. 按节点区块顺序组装 assembled_context（每区块归一化，JSON 块保留缩进）
        from utils.prompt_normalizer import normalize_text_block
        _JSON_SECTIONS = {"plot_list", "review_result"}
        ordered = []
        for sec_name, _ in assembly["sections"]:
            if sec_name in sections:
                header = RESOURCE_REGISTRY[sec_name]["header"]
                body = sections[sec_name]
                if sec_name not in _JSON_SECTIONS:
                    body = normalize_text_block(body, mode="preserve_md_list")
                ordered.append(f"{header}\\n{body}")
        ctx["assembled_context"] = normalize_text_block(
            "\\n\\n".join(ordered), mode="preserve_md_list")
        ctx["sections"] = sections
        return ctx'''
if old_as not in ct:
    raise SystemExit("装配归一化点未找到")
ct = ct.replace(old_as, new_as, 1)
print("[OK] context_analyzer: 装配上下文归一化")

# 3c. _build_analysis_prompt 返回前归一化
old_ap = '''        try:
            return user_prompt.format(
                chapter_index=chapter_index,
                step_name=step_name,
                step_description=step_description,
                focus=focus,
                resource_catalog=resource_catalog,
                rag_candidates_text=rag_candidates_text,
                prev_step_selections_text=prev_step_selections_text,
                dimension_checklist_text=dimension_checklist_text,
                output_schema=output_schema,
            )
        except KeyError as e:'''
new_ap = '''        try:
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
        except KeyError as e:'''
if old_ap not in ct:
    raise SystemExit("分析 prompt 归一化点未找到")
ct = ct.replace(old_ap, new_ap, 1)
print("[OK] context_analyzer: 分析 prompt 归一化")

with open(p_ctx, "w", encoding="utf-8", newline="\n") as f:
    f.write(ct)
py_compile.compile(p_ctx, doraise=True)
print("全部接入完成")
