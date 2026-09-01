---
system_prompt: 你是一位专业的网文反派设计师，擅长创造有深度、有动机的反派角色
user_prompt: |
  请为以下网文项目设计反派角色：
  
  【项目信息】
  书名：{project.title}
  题材：{project.genre}
  主角：{protagonist.name}
  主角缺陷：{project.protagonist_flaw}
  主角欲望：{project.protagonist_desire}
  
  【用户反派设定】
  反派分层级别：{project.antagonist_level}
  反派分层详情：{project.antagonist_tiers_desc}
  镜像对抗：{project.villain_mirror}
  （注：以上为用户已确定的反派基础设定，请在此基础上展开详细反派设计）
  
  【题材角色指南】
  {genre_character_guidelines}
  
  【题材核心卖点】
  {genre_core_selling_points}
  
  【设计要求】
  1. 基本信息：名称、身份/势力、出场时机
  2. 反派分层：小反派（前期）、中反派（中期）、大反派（后期）
  3. 核心驱动：核心欲望、核心恐惧、行动原则
  4. 镜像对抗：与主角共享的欲望/缺陷、反派道路、价值观冲突点
  5. 能力与资源：实力层级、关键能力/手段、组织/资源支持
  6. 规则与代价：被限制的规则、代价机制、反制点（主角可利用）
  7. 关键剧情节点：第一次正面交锋、中期压制点、失败/反转节点、终局命运
  8. 复杂度：是否可洗白/转化、是否存在更高层反派
  9. 反派进阶路径：反派升级/换挡节奏、权力阶梯/势力扩张方式
  
  【输出格式】JSON格式，包含以下字段：
  {{
    "name": "反派名称",
    "identity_faction": "身份/势力",
    "appearance_timing": "出场时机",
    "core_desire": "核心欲望",
    "core_fear": "核心恐惧",
    "action_principle": "行动原则",
    "shared_desire_flaw": "共享欲望/缺陷",
    "villain_path": "反派道路",
    "value_conflict_points": "价值观冲突点",
    "power_level": "实力层级",
    "key_abilities": "关键能力/手段",
    "organization_resources": "组织/资源支持",
    "restricted_rules": "被限制的规则",
    "cost_mechanism": "代价机制",
    "counter_points": "反制点",
    "can_be_redeemed": 0或1,
    "has_higher_villain": 0或1,
    "upgrade_rhythm": "升级/换挡节奏",
    "power_ladder": "权力阶梯/势力扩张方式",
    "hierarchy": [
      {{"tier": "小反派", "villain_name": "名称", "stage": "阶段", "goal": "目标", "protagonist_relation": "与主角关系"}}
    ],
    "plot_nodes": [
      {{"node_type": "首次交锋", "chapter": 章节号, "description": "描述"}}
    ]
  }}
---