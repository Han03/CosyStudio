# -*- coding: utf-8 -*-
"""T5 草稿 prompt 固定指令精简：合并通用要求，保留全部关键约束。"""
p = r"C:\MyProjects\CosyStudio\backend\webnovel\prompts\draft_generate_prompt.md"
with open(p, encoding="utf-8") as f:
    t = f.read()

old = '''  【写作要求】
  {user_prompt_section}
  用朴素直白的语言叙述事件经过、角色行为和关键对话;
  字数{draft_word_min}-{draft_word_max}字;
  每个剧情点独占一段，每段不超过{draft_point_max}字（1-3句），严禁将多个剧情点塞入同一段;
  对话单独成段，每句对话独占一行;
  禁止出现超过100字的密集段落;
  段落之间用空行分隔（一个空行），严禁不用空行;
  不要写环境氛围渲染、心理独白、五感描写和比喻等修辞;
  对话只保留核心意思，句子可以简短;
  注意节奏控制，保持读者兴趣;
  确保情节连贯，逻辑合理;
  避免重复描写，保持新鲜感;
  必须包含至少2个冲突点或转折点;
  {continue_prev}
  达到字数要求后自然停止，不要额外追加一段专门用来收尾总结的句子;'''
new = '''  【写作要求】
  {user_prompt_section}
  用朴素直白的语言叙述事件经过、角色行为和关键对话，不要环境氛围渲染、心理独白、五感描写和比喻等修辞;
  字数{draft_word_min}-{draft_word_max}字;每个剧情点独占一段，每段不超过{draft_point_max}字（1-3句），严禁多剧情点塞入同一段;
  对话单独成段，每句独占一行;段落间用空行分隔;禁止超过100字的密集段落;
  节奏连贯、逻辑合理、避免重复描写;必须包含至少2个冲突点或转折点;
  {continue_prev}
  达到字数要求后自然停止，不要额外追加收尾总结句;'''
if old not in t:
    raise SystemExit("写作要求未找到")
t = t.replace(old, new, 1)
with open(p, "w", encoding="utf-8", newline="\n") as f:
    f.write(t)
print(f"[OK] 写作要求精简：{len(old)} -> {len(new)} 字符（-{len(old)-len(new)}）")
