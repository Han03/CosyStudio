---
system_prompt: 你是一位专业的网文金手指设计师，擅长设计有趣且有平衡感的金手指系统
user_prompt: |
  请为以下网文项目设计金手指系统：
  
  【项目信息】
  书名：{project.title}
  题材：{project.genre}
  主角：{protagonist.name}
  主角缺陷：{protagonist.personality_flaw}
  
  【用户已定金手指信息】
  类型：{golden_finger.type}
  名称：{golden_finger.name}
  风格：{golden_finger.style}
  可见度：{golden_finger.visibility}
  不可逆代价：{golden_finger.irreversible_cost}
  （注：以上为用户已确定的基础设定，请在此基础上展开完整设计，类型和名称必须保持一致；若全部为空则自由设计）
  
  【题材核心卖点】
  {genre_core_selling_points}
  
  【题材金手指指南】
  {genre_golden_finger_guidelines}
  
  【题材故事规则】
  {genre_story_rules}
  
  【设计要求】
  1. 设定定位：题材适配点、主要作用（推进主线/解决硬约束/放大爽点）、读者可见度（明牌/半明牌/暗牌）
  2. 类型选择：系统/空间/位面穿梭/重生记忆/传承/血脉/召唤等
  3. 核心功能：功能描述、可视化表现、触发条件
  4. 获得方式：触发事件、代价/限制、不可逆代价
  5. 使用规则：冷却/次数限制、禁止事项、失败惩罚、反制方式
  6. 升级路线：初始形态 → 中期提升 → 最终形态
  7. 爽点嵌入：获得爽、成长爽、使用爽
  8. 反馈节奏：关键反馈节点、代价兑现节点、反转节点
  
  【输出格式】JSON格式，包含以下字段：
  {{
    "genre_fit": "题材适配点",
    "main_role": "主要作用",
    "visibility": "读者可见度",
    "type": "金手指类型",
    "core_function": "核心功能描述",
    "visual_expression": "可视化表现",
    "trigger_condition": "触发条件",
    "acquisition_event": "触发事件",
    "cost_limitation": "代价/限制",
    "irreversible_cost": "不可逆代价",
    "cooldown_limit": "冷却/次数限制",
    "forbidden_items": "禁止事项",
    "failure_penalty": "失败惩罚",
    "counter_method": "反制方式",
    "upgrade_path": [
      {{"stage": "初始形态", "description": "描述"}},
      {{"stage": "中期提升", "description": "描述"}},
      {{"stage": "最终形态", "description": "描述"}}
    ],
    "payoff_points": [
      {{"type": "获得爽", "description": "描述"}},
      {{"type": "成长爽", "description": "描述"}},
      {{"type": "使用爽", "description": "描述"}}
    ],
    "feedback_nodes": [
      {{"type": "关键反馈", "chapter_interval": N, "description": "描述"}},
      {{"type": "代价兑现", "chapter_interval": N, "description": "描述"}},
      {{"type": "反转节点", "chapter_interval": N, "description": "描述"}}
    ]
  }}
---