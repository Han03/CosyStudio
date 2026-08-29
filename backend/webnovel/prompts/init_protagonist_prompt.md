---
system_prompt: 你是一位专业的网文角色设计师，擅长设计角色关系和冲突。
user_prompt: |
  请为以下网文项目生成3套不同的主角设定与关系冲突方案。

  【项目信息】
  书名：{project_title}
  题材：{genre}
  一句话故事：{one_liner}
  核心冲突：{core_conflict}

  【用户已填主角信息】
  主角姓名：{protagonist_name}
  主角欲望：{protagonist_desire}
  主角缺陷：{protagonist_flaw}
  主角原型：{protagonist_archetype}
  反派镜像：{protagonist_villain_mirror}

  【生成要求】
  生成3套差异化的角色设定方案，每套包含：
  1. option_name: 方案名称（如"废柴逆袭型"、"重生复仇型"、"隐世传承型"）
  2. name: 主角姓名——必须是一个具体人物的姓名（2-4个汉字，如"林逸"、"苏晨"、"陈平安"），禁止使用家族名、势力名、群体称谓（如"李氏家族"、"王家"、"族人"），即使是家族型故事也必须给出具体人名
  3. desire: 主角欲望（最想要的是什么）
  4. flaw: 主角缺陷（会导致主角付出代价的缺陷）
  5. archetype: 主角原型
  6. structure: 主角结构（单主角/多主角）
  7. villain_mirror: 反派镜像一句话
  8. heroine_config: 感情线配置（无女主/单女主/多女主）
  9. antagonist_level: 反派分层（BOSS级/多级反派）
  10. scoring: 五维评分（每项1-10分，含理由）

  注意：如果用户已填写某个字段，至少有一套方案应保留用户输入；其他方案可提供不同方向。

  【输出格式】JSON格式，包含options数组。每套方案必须包含scoring字段，示例：
  {{
    "options": [
      {{
        "option_name": "xxx",
        "name": "xxx",
        "desire": "xxx",
        "flaw": "xxx",
        "archetype": "xxx",
        "structure": "单主角",
        "villain_mirror": "xxx",
        "heroine_config": "单女主",
        "antagonist_level": "BOSS级",
        "scoring": {{
          "creativity": {{"score": 8, "reason": "xxx"}},
          "feasibility": {{"score": 7, "reason": "xxx"}},
          "market_appeal": {{"score": 9, "reason": "xxx"}},
          "sustainability": {{"score": 7, "reason": "xxx"}},
          "emotional_impact": {{"score": 8, "reason": "xxx"}}
        }}
      }}
    ]
  }}
---
