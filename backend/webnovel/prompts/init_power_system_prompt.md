---
system_prompt: 你是一位专业的网文力量体系设计师，擅长构建逻辑严密、有层次感的力量体系
user_prompt: |
  请为以下网文项目设计力量体系：
  
  【项目信息】
  书名：{project.title}
  题材：{project.genre}
  主角金手指：{golden_finger.type}
  
  【用户力量体系设定】
  体系类型：{project.power_system_type}
  境界链：{project.cultivation_chain}
  （注：以上为用户已确定的力量体系基础设定，请在此基础上展开设计，体系类型和境界链必须保持一致）
  
  【题材力量体系】
  {genre_power_system}
  
  【题材世界观】
  {genre_worldview}
  
  【金手指设计知识】
  {golden_finger_knowledge}
  
  【设计要求】
  1. 体系公理：核心信条/定律、代价规则、公平性原则
  2. 体系类型：境界/等级/职业/血脉/契约/科技/双轨制
  3. 典型境界链：如练气-筑基-金丹-元婴...
  4. 能力来源：能量/资源来源、训练/修炼方法、社会控制机制
  5. 等级体系：等级顺序、每级核心能力
  6. 晋级条件：资源要求、突破方式、失败代价、越级代价
  7. 资源系统：核心资源类型、获取方式、稀缺性规则
  8. 战斗规则：伤害与防御逻辑、战斗节奏特点、克制/反制关系
  9. 禁忌与限制：禁术/禁地、高阶限制、硬限制
  10. 体系漏洞：漏洞描述、主角如何利用、反派如何反制
  
  【输出格式】JSON格式，包含以下字段：
  {{
    "core_creed": "核心信条",
    "cost_rules": "代价规则",
    "fairness_principle": "公平性原则",
    "system_type": "体系类型",
    "typical_realm_chain": "境界链",
    "small_realm_divisions": "小境界划分",
    "energy_source": "能量来源",
    "training_methods": "修炼方法",
    "social_control_mechanism": "社会控制机制",
    "power_levels": [
      {{"level_order": 1, "level_name": "等级名", "core_abilities": "核心能力", "resource_requirements": "资源要求", "breakthrough_method": "突破方式", "failure_cost": "失败代价", "overlevel_cost": "越级代价"}}
    ],
    "resource_types": ["资源类型1", "资源类型2"],
    "resource_acquisition": "获取方式",
    "scarcity_rules": "稀缺性规则",
    "damage_defense_logic": "伤害与防御逻辑",
    "battle_rhythm": "战斗节奏特点",
    "counter_relations": "克制/反制关系",
    "escape_mechanism": "逃生/撤退机制",
    "forbidden_arts": "禁术/禁地",
    "high_level_limits": "高阶限制",
    "hard_limits": "硬限制",
    "system_vulnerabilities": "体系漏洞",
    "protagonist_exploitation": "主角如何利用",
    "villain_counter": "反派如何反制",
    "power_feedbacks": [
      {{"feedback_type": "类型", "chapter_interval": N, "description": "描述"}}
    ]
  }}
---