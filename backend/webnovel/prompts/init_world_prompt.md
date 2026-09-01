---
system_prompt: 你是一位专业的网文世界观设计师。
user_prompt: |
  请为以下网文项目设计3套不同的世界观方案。

  【项目信息】
  书名：{project_title}
  题材：{genre}
  一句话故事：{one_liner}
  核心冲突：{core_conflict}
  目标字数：{target_words}
  目标章节：{target_chapters}
  目标读者：{target_reader}
  目标平台：{platform}

  【主角设定】
  主角姓名：{protagonist_name}
  主角欲望：{protagonist_desire}
  主角缺陷：{protagonist_flaw}
  主角原型：{protagonist_archetype}
  主角结构：{protagonist_structure}

  【关系配置】
  感情线配置：{heroine_config}
  反派分层：{antagonist_level}
  反派镜像：{antagonist_mirror}

  【金手指设定】
  金手指类型：{gf_type}
  金手指名称：{gf_name}
  金手指风格：{gf_style}
  可见度：{gf_visibility}

  【用户已填世界观信息】
  世界观复杂度：{world_complexity}
  力量体系：{power_system}
  地理设定：{geography}
  历史背景：{history}
  关键地点：{key_locations}

  【生成要求】
  生成3套差异化的世界观方案，每套包含：
  1. option_name: 方案名称（如"经典修仙大陆"、"都市异能世界"、"废土科技世界"）
  2. scale: 世界规模（单城/多城/大陆/多界）
  3. power_system_type: 力量体系类型（修仙/武道/魔法/科技/异能/职场/无）
  4. factions: 势力格局（换行分隔的字符串）
  5. social_class: 社会阶层与资源分配（换行分隔的字符串）
  6. currency_system: 货币体系（换行分隔的字符串）
  7. cultivation_chain: 境界链（换行分隔的字符串）
  8. sect_hierarchy: 宗门/组织层级（换行分隔的字符串）
  9. scoring: 五维评分（每项1-10分，含理由）

  注意：如果用户已填写某个字段，至少有一套方案应保留用户输入；其他方案可提供不同方向。所有字段必须是字符串类型。

  【输出格式】JSON格式，包含options数组。每套方案必须包含scoring字段，示例：
  {{
    "options": [
      {{
        "option_name": "xxx",
        "scale": "大陆",
        "power_system_type": "修仙",
        "factions": "xxx",
        "social_class": "xxx",
        "currency_system": "xxx",
        "cultivation_chain": "xxx",
        "sect_hierarchy": "xxx",
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
