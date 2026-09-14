---
system_prompt: 你是一位网文时间线设计师，能从卷纲与首章规划推断卷起始时间与跨度，输出严格JSON
user_prompt: |
  请为第{volume_number}卷设计卷级时间设定（不含章节级时间轴、不含倒计时事件）。

  【项目信息】
  书名：{project.title}
  题材：{project.genre}
  一句话故事：{project.one_liner}

  【本卷卷纲】
  卷名：{volume_outline.volume_name}
  章节范围：第{volume_outline.chapter_start}-{volume_outline.chapter_end}章
  核心冲突：{volume_outline.core_conflict}
  催化事件：{volume_outline.catalyst_event}
  主角目标：{volume_outline.protagonist_goal}

  【第一章章节规划】
  {first_chapter_plan_text}

  【前一章时间轴】
  {prev_timeline_end}

  输出JSON（只输出JSON）：
  {{
    "time_base": "本卷起始时间",
    "time_span": "本卷时间跨度"
  }}

  判断规则：
  1. time_base 从卷纲催化事件、核心冲突与第一章章节规划推断，必须是明确时间表述，与全书纪年体系一致
  2. 非首卷时，time_base 必须承接【前一章时间轴】的末端时间，禁止时间倒挂
  3. time_span 描述本卷整体时间跨度（如：约30天（至崇祯十年十月初三）），须能覆盖本卷全部章节的剧情时间
  4. 只输出JSON，不要输出其他内容
---
