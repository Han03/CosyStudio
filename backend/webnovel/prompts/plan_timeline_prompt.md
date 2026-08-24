---
system_prompt: 你是一位专业的网文时间线设计师，擅长构建严谨、有逻辑的时间轴
user_prompt: |
  请为第{volume_number}卷设计时间线。
  
  【项目信息】
  书名：{project.title}
  题材：{project.genre}
  一句话故事：{project.one_liner}
  
  【卷纲约束】
  卷名：{volume_outline.volume_name}
  章节范围：{volume_outline.chapter_start}-{volume_outline.chapter_end}
  核心冲突：{volume_outline.core_conflict}
  
  【章节规划】
  {chapter_plans_text}
  
  【主角信息】
  姓名：{protagonist.name}
  
  【设计要求】
  1. 卷级时间设定：时间基准、本卷时间跨度、关键倒计时事件
  2. 章节时间轴：参考上述章节规划内容，为每个章节设定时间锚点、章内跨度、与上章间隔、倒计时状态，确保时间线与章节剧情一致
  3. 倒计时事件追踪：事件名称、起始倒计时、当前状态、触发章节、结果
     - current_status 必须填写 "未触发"（此时为初始化阶段，故事尚未开始）
  
  【时间规则】
  - 同日内连续：无需特殊交代
  - 跨夜（6-12小时）：需1-2句过渡
  - 跨日（1-3天）：需过渡段落或过渡章
  - 大跨度（>3天）：必须有过渡章或明确时间标记
  - 禁止时间回跳（除非是明确的回忆/闪回）
  - 禁止倒计时跳跃
  
  【输出格式】JSON格式，包含以下字段：
  {{
    "time_base": "时间基准",
    "time_span": "本卷时间跨度",
    "countdown_events": ["倒计时事件1", "倒计时事件2"],
    "chapter_timeline": [
      {{
        "chapter_number": 章节号,
        "time_anchor": "时间锚点",
        "chapter_duration": "章内跨度",
        "interval_from_prev": "与上章间隔",
        "countdown_status": "倒计时状态",
        "notes": "备注"
      }}
    ],
    "countdown_tracking": [
      {{
        "event_name": "事件名称",
        "start_countdown": "起始倒计时",
        "current_status": "固定填写：未触发",
        "trigger_chapter": 触发章节,
        "result": "结果"
      }}
    ]
  }}
---