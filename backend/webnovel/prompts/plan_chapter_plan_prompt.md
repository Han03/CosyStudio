---
system_prompt: 你是一位专业的网文章纲设计师，擅长设计行云流水、读不出章节边界的章节结构
user_prompt: |
  请为第{volume_number}卷的第{batch_chapter_start}-{batch_chapter_end}章设计章节规划（第{batch_index}/{total_batches}批）：

  【项目信息】
  书名：{project.title}
  题材：{project.genre}

  【卷纲约束】
  卷名：{volume_outline.volume_name}
  全卷章节范围：{volume_outline.chapter_start}-{volume_outline.chapter_end}
  本批章节范围：{batch_chapter_start}-{batch_chapter_end}
  核心冲突：{volume_outline.core_conflict_desc}
  卷末高潮：{volume_outline.volume_climax_desc}
  开卷承诺：{volume_outline.promise_description_desc}
  催化事件：{volume_outline.catalyst_event_desc}
  危机链：{volume_outline.crises}
  中段反转：{volume_outline.mid_reversal_desc}

  【主角信息】
  姓名：{protagonist.name}
  欲望：{protagonist.desire}
  缺陷：{protagonist.flaw}

  【主角团信息】
  共同目标：{character_group.common_goal}
  阶段目标：{character_group.stage_goal}
  团队成员：{character_group_members}

  【前序批次摘要】
  {previous_batch_summary}

  【设计要求】
  为本批每一章（第{batch_chapter_start}章到第{batch_chapter_end}章）分别设计：
  1. 章节标题
  2. 概要：本章要发生的事情
  3. 目标：本章主角要达成的目标
  4. 阻力：主角面临的阻力/障碍
  5. 代价：主角付出的代价
  6. 关键事件：必须发生的事件（按顺序）
  7. 预期爽点：本章的爽点设计
  8. 伏笔埋设/回收：本章涉及的伏笔
  9. 收尾方式：从以下自然停点中为每章选择一种——动作/对话进行到一半切断、情绪落点安静收束、信息差留白、危机骤起（慎用，连续章节最多出现一次）；相邻章节禁止使用相同收尾方式

  【结构化节点规范】
  - CBN (Chapter Beginning Node)：章首节点，每章固定1个，格式为"主体 | 动作/变化 | 对象/结果"
  - CPNs (Chapter Progress Nodes)：章中推进节点，每章2-4个，按时间顺序排列，格式同上
  - CEN (Chapter Ending Node)：章末节点，每章固定1个，格式同上
  - must_cover_nodes：必须覆盖节点，最多4个，建议CBN + CEN + 1~2个核心CPN
  - forbidden_zones：本章禁区，不超过5条，只写本章绝对不能发生的硬禁区
  - 相邻章节 CEN → 下一章 CBN 必须逻辑承接

  【输出格式】JSON格式，chapter_plans 数组中必须包含本批全部章节（共{batch_size}章）：
  {{
    "chapter_plans": [
      {{
        "chapter_index": 章节号,
        "chapter_title": "章节标题",
        "summary": "概要",
        "chapter_goal": "目标",
        "resistance": "阻力",
        "cost": "代价",
        "key_events": ["事件1", "事件2", "事件3"],
        "expected_cool_points": "预期爽点",
        "foreshadowing": "伏笔埋设/回收",
        "chapter_hook": "收尾方式",
        "time_anchor": "时间锚点",
        "chapter_duration": "章内跨度",
        "interval_from_prev": "与上章间隔",
        "countdown_status": "倒计时状态",
        "strand": "Strand类型(quest/fire/constellation)",
        "villain_tier": "反派层级",
        "perspective": "视角/主角",
        "key_entities": "关键实体",
        "chapter_change": "本章变化",
        "unresolved_questions": "章末未闭合问题（可为空）",
        "cbn": "章首节点",
        "cpns": ["推进节点1", "推进节点2"],
        "cen": "章末节点",
        "must_cover_nodes": ["必须覆盖节点1", "必须覆盖节点2"],
        "forbidden_zones": ["禁区1", "禁区2"]
      }}
    ]
  }}
---
