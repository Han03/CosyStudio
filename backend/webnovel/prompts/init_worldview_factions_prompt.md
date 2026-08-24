---
system_prompt: 你是一位专业的网文世界观设计师，擅长设计复杂的势力格局和历史脉络
user_prompt: |
  请为以下网文项目设计势力格局和历史年表：

  【项目信息】
  书名：{project.title}
  题材：{project.genre}

  【已有世界观】
  世界简介：{worldview.world_summary}
  社会阶层：{worldview.social_hierarchy}
  核心区域：{worldview.core_regions}
  资源分配：{worldview.resource_distribution}

  【用户已有势力数据】
  {existing_factions_text}

  【用户已有历史数据】
  {existing_history_text}

  【题材世界观参考】
  {genre_worldview}

  【势力格局设计要求】
  1. 如果用户已有势力数据，请在此基础上补充完善（添加层级、关系、组织结构），而非重复生成；如果没有，请全新设计 3-6 个核心势力
  2. 每个势力需包含：势力名称、层级定位（顶级/一流/二流/新兴）、与其他势力的关系、内部组织结构
  3. 势力之间要有明确的矛盾和利益冲突
  4. 至少有一个隐藏势力或暗线势力

  【历史年表设计要求】
  1. 如果用户已有历史数据，请在此基础上补充完善，而非重复生成；如果没有，请全新设计 3-6 个关键历史事件节点
  2. 每个事件需包含时代标签和事件描述
  3. 事件之间要有因果逻辑链
  4. 至少有一个事件与当前主线矛盾直接相关

  【输出格式】JSON格式，包含以下字段：
  {{
    "factions": [
      {{"faction_name": "势力名", "tier": "层级定位", "relation": "与其他势力关系", "hierarchy": "内部组织结构"}}
    ],
    "history_events": [
      {{"era": "时代标签", "event": "事件描述"}}
    ]
  }}
---
