---
system_prompt: 你是一位专业的网文角色设计师，擅长创造立体、有魅力的角色
user_prompt: |
  请为以下网文项目设计{character_type}角色：
  
  【项目信息】
  书名：{project.title}
  题材：{project.genre}
  金手指：{golden_finger.type}
  
  {character_basic_section}
  
  【题材角色指南】
  {genre_character_guidelines}
  
  【题材核心卖点】
  {genre_core_selling_points}
  
  【设计要求】
  1. 基本信息：姓名、年龄、身份、起点状态
  2. 核心标签：3个关键词，读者第一印象
  3. 性格与底色：核心性格、行为底线、情绪触发点
  4. 动机与目标：短期/中期/长期目标，真正渴望（可能不自知）
  5. 缺陷与代价：性格缺陷、能力限制、心理阴影
  6. 行为模式：常用解决方式、失败时的本能反应、破局特长
  7. 成长弧线：阶段1（起点）→ 阶段2（变化）→ 阶段3（蜕变）
  8. OOC警戒：绝不该做的事、需要提前铺垫的事
  
  【输出格式】JSON格式，包含以下字段：
  {{
    "name": "角色名",
    "age": 年龄,
    "identity": "身份",
    "starting_state": "起点状态",
    "core_tags": ["标签1", "标签2", "标签3"],
    "first_impression": "读者第一印象",
    "core_personality": "核心性格",
    "behavior_bottom_line": "行为底线",
    "emotion_triggers": "情绪触发点",
    "easy_to_anger": "易激怒点",
    "easy_to_soften": "容易心软点",
    "short_term_goal": "短期目标",
    "medium_term_goal": "中期目标",
    "long_term_goal": "长期目标",
    "true_desire": "真正渴望",
    "personality_flaw": "性格缺陷",
    "ability_limit": "能力限制",
    "psychological_shadow": "心理阴影",
    "cost_tolerance": "代价承受底线",
    "behavior_pattern": "常用解决方式",
    "failure_reaction": "失败时的本能反应",
    "breakthrough_strength": "破局特长",
    "growth_arc": {{
      "stage1": "阶段1描述",
      "stage2": "阶段2描述",
      "stage3": "阶段3描述"
    }},
    "ooc_warnings": ["绝不该做的事1", "绝不该做的事2"],
    "need_foreshadowing": ["需要提前铺垫的事"]
  }}
---