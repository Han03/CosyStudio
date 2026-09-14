# -*- coding: utf-8 -*-
"""三个纯文本节点调用 parse_llm_json 传 expect_json=False。"""
import py_compile

files = [
    # (path, old, new)
    (
        r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\draft_generator_executor.py",
        '''            draft_data = parse_llm_json(
                response_content,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name=f"draft_chapter_{chapter_index}",
            )''',
        '''            draft_data = parse_llm_json(
                response_content,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name=f"draft_chapter_{chapter_index}",
                expect_json=False,
            )''',
    ),
    (
        r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\draft_polisher_executor.py",
        '''            polished_data = parse_llm_json(
                raw_content,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="draft_polish",
            )''',
        '''            polished_data = parse_llm_json(
                raw_content,
                script_id=script_id,
                project_id=project_id,
                executor_name=self.step_name,
                prompt_name="draft_polish",
                expect_json=False,
            )''',
    ),
    (
        r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\executors\draft_reviewer_executor.py",
        '''        revised_data = parse_llm_json(
            raw_content,
            script_id=self.script_id,
            project_id=project_id,
            executor_name="draft_reviewer_revise",
            prompt_name="revise_draft",
        )''',
        '''        revised_data = parse_llm_json(
            raw_content,
            script_id=self.script_id,
            project_id=project_id,
            executor_name="draft_reviewer_revise",
            prompt_name="revise_draft",
            expect_json=False,
        )''',
    ),
]

for path, old, new in files:
    with open(path, encoding="utf-8") as f:
        t = f.read()
    if old not in t:
        print(f"[SKIP] {path}: 未找到")
        continue
    t = t.replace(old, new, 1)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(t)
    py_compile.compile(path, doraise=True)
    print(f"[OK] {path.split(chr(92))[-1]}")

print("完成")
