---
system_prompt: 你是一位拥有10年经验的顶级网文编辑和创意策划师，擅长为网文项目设计独特的创意约束和卖点定位。
user_prompt: |
  请为以下网文项目设计2-3套创意约束包方案。

  【项目信息】
  书名：{project_title}
  题材：{genre}
  一句话故事：{one_liner}
  核心冲突：{core_conflict}
  主角姓名：{protagonist_name}
  主角欲望：{protagonist_desire}
  主角缺陷：{protagonist_flaw}
  金手指类型：{gf_type}
  金手指名称：{gf_name}
  世界规模：{world_scale}
  力量体系类型：{power_system_type}

  【用户已填约束信息】
  单章字数：{word_count_chapter}
  是否序言：{prologue}
  第一章设计：{first_chapter}
  文风：{style}
  套路清单：{tropes}

  【生成要求】
  为这个项目生成3套创意约束包方案，每套只包含以下4个字段（与前端表单一致，不要生成多余字段）：
  1. anti_trope_rule: 反套路规则1条（与常规题材写法形成反差）
  2. hard_constraints: 硬约束2-3条（必须遵守的硬性规则，增加故事张力）
  3. core_selling_points: 核心卖点（一句话讲清本书的独特卖点）
  4. opening_hook: 开篇钩子（吸引读者继续阅读的开篇设计）

  注意：如果用户已填写某个字段，请保留或基于用户输入进行优化；如果用户未填写，则根据项目信息、主角设定、金手指和世界观进行创作。

  【输出格式】JSON格式，包含constraint_packages数组。示例格式：
  {{
    "constraint_packages": [
      {{
        "anti_trope_rule": "xxx",
        "hard_constraints": ["xxx", "xxx"],
        "core_selling_points": "xxx",
        "opening_hook": "xxx"
      }}
    ]
  }}
---
