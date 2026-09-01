---
system_prompt: 你是一位拥有10年经验的顶级网文编辑和创意策划师，擅长为网文项目定位故事方向和商业模式。
user_prompt: |
  请为以下网文项目生成3套不同的故事核与商业定位方案。

  【已知信息】
  书名：{title}
  用户选择题材：{genre_display}

  【用户已填信息】
  一句话故事：{one_liner_display}
  核心冲突：{core_conflict_display}

  【生成要求】
  生成3套差异化的故事定位方案，每套包含：
  1. option_name: 方案名称（简洁有力，如“商业燃文路线”、“深度剧情路线”、“创新实验路线”）
  2. genre: 最匹配的题材（必须从以下系统支持的题材中选择，不得自创：{genre_list_str}）
  3. one_liner: 一句话故事（必须能一句话讲清且不撞模板）
  4. core_conflict: 核心冲突
  5. target_words: 目标字数（数字）
  6. target_chapters: 目标章节（数字）
  7. target_reader: 目标读者
  8. platform: 目标平台
  9. scoring: 五维评分（每项1-10分，含理由）：
     - creativity: 创意独特性
     - feasibility: 落地可行性
     - market_appeal: 市场吸引力
     - sustainability: 长线可持续性
     - emotional_impact: 情感冲击力
  
  重要约束：one_liner、core_conflict、target_reader 等所有生成字段中禁止出现任何人名（包括主角名、配角名、虚构人名等），用身份称谓代替（如“少年”“废柴少年”“天才少女”等）。此时角色尚未设定，不应出现具体人名。
  
  注意：如果用户已选择题材，至少有一套方案应使用该题材；其他方案可以推荐更适合该故事方向的不同题材。genre 字段必须严格使用上述列表中的题材名称。

  【输出格式】JSON格式，包含options数组。示例：
  {{
    "options": [
      {{
        "option_name": "方案A：xxx",
        "genre": "{example_genre}",
        "one_liner": "xxx",
        "core_conflict": "xxx",
        "target_words": 1000000,
        "target_chapters": 200,
        "target_reader": "xxx",
        "platform": "xxx",
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
