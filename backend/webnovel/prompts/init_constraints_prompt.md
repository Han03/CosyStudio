---
system_prompt: 你是一位拥有10年经验的顶级网文编辑和创意策划师，擅长为网文项目设计独特的创意约束和卖点定位。
user_prompt: |
  请为以下网文项目设计3套创意约束包方案。

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

  【世界观设定】
  世界规模：{world_scale}
  力量体系类型：{power_system_type}
  势力格局：{factions}
  社会阶层：{social_class}
  货币体系：{currency_system}
  境界链：{cultivation_chain}
  宗门/组织层级：{sect_hierarchy}

  【用户已填约束信息】
  反套路规则：{anti_trope}
  硬性约束：{hard_constraints}
  核心卖点：{core_selling_points}
  开篇钩子：{opening_hook}

  【生成要求】
  为这个项目生成3套创意约束包方案，每套包含以下4个内容字段 + 1个评分对象（与前端表单一致）：
  1. anti_trope_rule: 反套路规则1条（与常规题材写法形成反差）
  2. hard_constraints: 硬约束2-3条（必须遵守的硬性规则，增加故事张力）
  3. core_selling_points: 核心卖点（一句话讲清本书的独特卖点）
  4. opening_hook: 开篇钩子（吸引读者继续阅读的开篇设计）
  5. scoring: 五维评分（每项1-10分，含理由）：
     - creativity: 创意独特性
     - feasibility: 落地可行性
     - market_appeal: 市场吸引力
     - sustainability: 长线可持续性
     - emotional_impact: 情感冲击力

  注意：如果用户已填写某个字段，请保留或基于用户输入进行优化；如果用户未填写，则根据项目信息、主角设定、金手指和世界观进行创作。

  【输出格式】JSON格式，包含constraint_packages数组。示例格式：
  {{
    "constraint_packages": [
      {{
        "anti_trope_rule": "xxx",
        "hard_constraints": ["xxx", "xxx"],
        "core_selling_points": "xxx",
        "opening_hook": "xxx",
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
