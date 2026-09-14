# -*- coding: utf-8 -*-
"""一次性补丁：orchestrator.py 两处修改（CRLF 安全）。
1. execute_pipeline 开头调用 _normalize_word_config()（字数参数化接通真实链路）
2. 步骤失败即中断（break），不再继续后续步骤
用法：python _patch_orchestrator.py
"""
import io

PATH = r"C:\MyProjects\CosyStudio\backend\webnovel\pipeline\orchestrator.py"

with io.open(PATH, "r", encoding="utf-8", newline="") as f:
    text = f.read()

crlf = "\r\n" in text

patches = [
    # 1. execute_pipeline 接入字数归一化
    (
        '        if not enable_polish and "draft_polisher" in steps:\n'
        '            steps.remove("draft_polisher")\n'
        '\n'
        '        self._context["user_prompt"] = user_prompt',
        '        if not enable_polish and "draft_polisher" in steps:\n'
        '            steps.remove("draft_polisher")\n'
        '\n'
        '        # 字数归一化：真实创作链路（execute_pipeline）也生效\n'
        '        self._normalize_word_config()\n'
        '\n'
        '        self._context["user_prompt"] = user_prompt',
    ),
    # 2a. 步骤失败即中断
    (
        '                else:\n'
        '                    failed_steps += 1\n'
        '                    self._logger.error(f"步骤 {step_name} 失败: {result.error_message}")\n'
        '                    await self._update_progress(\n'
        '                        current_progress,\n'
        '                        f"{step_display}失败: {result.error_message}",\n'
        '                        step_display\n'
        '                    )\n'
        '\n'
        '                current_progress += step_info["weight"]',
        '                else:\n'
        '                    failed_steps += 1\n'
        '                    self._logger.error(f"步骤 {step_name} 失败: {result.error_message}")\n'
        '                    await self._update_progress(\n'
        '                        current_progress,\n'
        '                        f"{step_display}失败: {result.error_message}",\n'
        '                        step_display\n'
        '                    )\n'
        '                    # 失败即中断：后续步骤缺失依赖继续执行只会产生无效产物\n'
        '                    break\n'
        '\n'
        '                current_progress += step_info["weight"]',
    ),
    # 2b. 执行异常即中断
    (
        '                await self._update_progress(\n'
        '                    current_progress,\n'
        '                    f"执行异常: {error_msg[:100]}",\n'
        '                    step_info.get("description", step_name) if executor_class else step_name\n'
        '                )\n'
        '\n'
        '        self._context["end_time"]',
        '                await self._update_progress(\n'
        '                    current_progress,\n'
        '                    f"执行异常: {error_msg[:100]}",\n'
        '                    step_info.get("description", step_name) if executor_class else step_name\n'
        '                )\n'
        '                # 执行异常即中断\n'
        '                break\n'
        '\n'
        '        self._context["end_time"]',
    ),
]

ok = True
for old, new in patches:
    if crlf:
        old = old.replace("\n", "\r\n")
        new = new.replace("\n", "\r\n")
    if old not in text:
        print(f"[FAIL] 未找到补丁目标: {old[:60]!r}")
        ok = False
        continue
    text = text.replace(old, new, 1)
    print(f"[OK] 补丁应用: {old[:50]!r}")

if ok:
    with io.open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("全部补丁已写入")
else:
    print("存在未应用的补丁，文件未写入")
