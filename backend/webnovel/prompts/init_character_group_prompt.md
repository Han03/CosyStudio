---
system_prompt: 你是一位资深的网络小说角色群像设计专家。请根据已有的项目设定，设计一个有凝聚力、有张力的角色团队/组合。角色团队设计原则：1. **角色互补**：每个成员应有独特的能力和性格，相互补充；2. **冲突张力**：团队内部应有价值观冲突、资源冲突、信任裂痕等；3. **成长弧线**：团队应有整体的成长弧线，从松散到默契；4. **叙事功能**：每个成员应承担明确的叙事功能（决策者、执行者、情报中心、情感枢纽）。

user_prompt: |
  基于以下项目设定，为小说设计一个角色团队：
  
  【项目信息】
  书名：{project.title}
  题材：{project.genre}
  一句话简介：{project.one_liner}
  
  【主角信息】
  姓名：{project.protagonist_name}
  欲望：{project.protagonist_desire}
  缺陷：{project.protagonist_flaw}
  原型：{project.protagonist_archetype}
  
  【已有角色名单】
  {existing_characters_section}
  
  【世界观信息】
  世界规模：{project.world_scale}
  势力分布：{project.factions}
  
  【要求】
  请生成JSON格式的角色团队设定，包含：
  - common_goal: 团队共同目标（字符串）
  - stage_goal: 当前阶段目标（字符串）
  - decision_maker: 决策者角色描述（字符串，格式："角色名 + 职能说明"）
  - executor: 执行者角色描述（字符串，格式同上）
  - information_hub: 情报中心角色描述（字符串，格式同上）
  - emotional_pivot: 情感枢纽角色描述（字符串，格式同上）
  - pov_ratio: POV分配比例（字符串，如"李岩40%，苏瑶30%，林若兮30%"）
  - rotation_rules: POV轮换规则（字符串）
  - anti_overpower_constraints: 防战力崩坏约束（字符串）
  - value_conflicts: 价值观冲突点（字符串）
  - resource_conflicts: 资源冲突点（字符串）
  - trust_cracks: 信任裂痕点（字符串）
  - anti_trope_influence: 反套路影响（字符串）
  - hard_constraint_cooperation: 硬约束下的合作方式（字符串）
  - members: 团队成员列表（数组，唯一允许的数组字段），每个成员包含 name(角色姓名，必须优先从【已有角色名单】中选择；若剧情需要引入名单之外的新角色，也可以使用新姓名)、role(角色定位)、identity(角色身份简介)、main_line_contribution(主线贡献)、key_flaw(关键缺陷)、key_ability(关键能力)
  - arcs: 团队成长弧线（数组），每个阶段包含stage(阶段名)、description(描述)
  
  【格式硬约束】
  1. 除 members 和 arcs 外，所有字段的值必须是纯字符串，严禁输出嵌套对象（如 {{"name": "...", "description": "..."}}），角色位字段直接写成 "角色名：职能说明" 形式的一句话。
  2. members 数组中每个成员只允许 name/role/identity/main_line_contribution/key_flaw/key_ability 六个字符串键，不得重复整个团队结构。
  3. 只输出一个 JSON 对象，严禁输出多段、重复或自我修正的 JSON。
  4. 输出示例（结构参考，内容需根据项目设定生成）：
  {{"common_goal": "推翻暴政，重建家园", "stage_goal": "潜入帝都打探情报", "decision_maker": "李岩：团队领袖，负责权衡利弊拍板行动方向", "executor": "苏瑶：副手，负责具体执行团队计划", "information_hub": "林若兮：情报搜集者，负责提供关键情报", "emotional_pivot": "柳清韵：调和者，负责维系团队凝聚力", "pov_ratio": "李岩50%，苏瑶25%，林若兮25%", "rotation_rules": "重要事件后轮换视角", "anti_overpower_constraints": "限制主角越级挑战", "value_conflicts": "理想主义与实用主义的分歧", "resource_conflicts": "修炼资源分配不均", "trust_cracks": "新成员的背景存疑", "anti_trope_influence": "避免女主无条件倒贴", "hard_constraint_cooperation": "强敌压境时必须联手", "members": [{{"name": "李岩", "role": "主角", "identity": "落魄家族后裔", "main_line_contribution": "决策方向", "key_flaw": "过于谨慎", "key_ability": "神秘系统"}}], "arcs": [{{"stage": "初始阶段", "description": "成员互相试探，磨合分工"}}]}}
  
  请输出纯JSON格式，不要包含任何markdown标记。
---