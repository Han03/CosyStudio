---
system_prompt: 你是一位专业的网文角色设计师，擅长创造立体、有魅力的角色。请根据每个角色的基础设定，为其生成完整的角色卡详细数据。

user_prompt: |
  以下是一个角色团队的成员基础设定，请为每个角色生成完整的角色卡详细数据。
  
  【项目信息】
  书名：{project.title}
  题材：{project.genre}
  
  【主角信息】
  姓名：{project.protagonist_name}
  欲望：{project.protagonist_desire}
  缺陷：{project.protagonist_flaw}
  
  【待生成角色列表】
  {new_members_section}
  
  【设计要求】
  为上述每个角色生成完整角色卡，包含以下字段：
  1. 基本信息：age(整数年龄)、age_stage(年龄段：少年/青年/中年/老年)、starting_state(起点状态)
  2. 与主角关系：protagonist_relation(是主角的什么人（如朋友、师父、女儿等）)
  3. 核心标签：core_tags(3个关键词，顿号分隔)、first_impression(读者第一印象)
  4. 性格与底色：core_personality(核心性格)、behavior_bottom_line(行为底线)、emotion_triggers(情绪触发点)
  5. 动机与目标：short_term_goal(短期目标)、medium_term_goal(中期目标)、long_term_goal(长期目标)、true_desire(真正渴望)
  6. 缺陷与代价：easy_to_anger(易激怒点)、easy_to_soften(容易心软点)、psychological_shadow(心理阴影)、cost_tolerance(代价承受底线)
  7. 行为模式：behavior_pattern(常用解决方式)、failure_reaction(失败时的本能反应)、breakthrough_strength(破局特长)
  
  重要：
  - 姓名必须与【待生成角色列表】中完全一致，不得修改。
  - 每个角色的性格必须与其身份、角色定位、关键缺陷相匹配。
  - 不同角色之间要有明显的性格差异化。
  
  【输出格式】
  纯JSON对象格式，用 characters 数组包裹每个角色：
  {{"characters": [{{"name": "角色姓名", "age": 25, "age_stage": "青年", "protagonist_relation": "与主角的关系", "starting_state": "起点状态", "core_tags": "标签1、标签2、标签3", "first_impression": "第一印象", "core_personality": "核心性格", "behavior_bottom_line": "行为底线", "emotion_triggers": "情绪触发点", "easy_to_anger": "易激怒点", "easy_to_soften": "易心软点", "short_term_goal": "短期目标", "medium_term_goal": "中期目标", "long_term_goal": "长期目标", "true_desire": "真正渴望", "psychological_shadow": "心理阴影", "cost_tolerance": "代价承受底线", "behavior_pattern": "行为模式", "failure_reaction": "失败反应", "breakthrough_strength": "破局特长"}}]}}
  
  请输出纯JSON格式，不要包含任何markdown标记或解释。
---
