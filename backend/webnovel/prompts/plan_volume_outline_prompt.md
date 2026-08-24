---
system_prompt: 你是一位专业的网文卷纲设计师，擅长构建有张力、有节奏的卷级结构
user_prompt: |
  请为以下网文项目的第{volume_number}卷设计卷纲：
  
  【项目信息】
  书名：{project.title}
  题材：{project.genre}
  
  【世界观】
  世界简介：{world.world_summary}
  社会结构：{world.social_hierarchy}
  主要势力：{factions_text}
  
  【总纲约束】
  卷名：{master_volume.volume_name}
  章节范围：{master_volume.chapter_range}
  核心冲突：{master_volume.core_conflict}
  卷末高潮：{master_volume.volume_climax}
  
  【当前状态】
  主角当前境界：{protagonist_power.realm}
  当前时间线：{current_timeline}
  
  【设计要求】
  1. 开卷承诺（Promise）：本卷读者承诺（爽点/悬念/情绪）、主要兑现类型
  2. 催化事件（Catalyst）：事件描述、不可逆变化、主角当下目标
  3. 升级危机链（Fichtean）：至少3次危机，每次危机/冲突、代价/风险升级、结果/变化
  4. 中段反转：假胜利/假失败/反转事件、反转带来的新认知/新代价
  5. 卷末最低谷（All Is Lost）：最低谷事件、代价、主角选择
  6. 卷末大兑现 + 新钩子：本卷兑现、新钩子、章末未闭合问题
  
  【输出格式】JSON格式，包含以下字段：
  {{
    "volume_number": {volume_number},
    "volume_name": "卷名",
    "chapter_start": 起始章,
    "chapter_end": 结束章,
    "core_conflict": "核心冲突",
    "volume_climax": "卷末高潮",
    "promise_description": "开卷承诺",
    "promise_types": ["兑现类型1", "兑现类型2"],
    "catalyst_event": "催化事件",
    "irreversible_change": "不可逆变化",
    "protagonist_goal": "主角当下目标",
    "crises": [
      {{"crisis_order": 1, "crisis_event": "危机事件", "cost_risk_upgrade": "代价升级", "result_change": "结果变化"}}
    ],
    "mid_reversal": "中段反转",
    "reversal_insight": "反转带来的新认知",
    "lowest_point_event": "最低谷事件",
    "lowest_point_cost": "代价",
    "protagonist_choice": "主角选择",
    "payoff_items": ["兑现1", "兑现2"],
    "new_hook": "新钩子",
    "unresolved_issues": "章末未闭合问题"
  }}
---