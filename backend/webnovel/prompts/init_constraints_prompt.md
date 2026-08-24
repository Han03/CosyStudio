---
system_prompt: 你是一位拥有10年经验的顶级网文编辑和创意策划师，擅长为网文项目设计独特的创意约束和卖点定位。

user_prompt: |
  请为以下网文项目设计2-3套创意约束包方案。
  
  【项目信息】
  书名：{project.title}
  题材：{project.genre}
  一句话故事：{project.one_liner}
  核心冲突：{project.core_conflict}
  目标读者：{project.target_reader}
  目标平台：{project.platform}
  
  【主角信息】
  姓名：{protagonist.name}
  欲望：{protagonist.desire}
  缺陷：{protagonist.flaw}
  原型：{protagonist.archetype}
  
  【金手指信息】
  类型：{golden_finger.type}
  名称：{golden_finger.name}
  不可逆代价：{golden_finger.irreversible_cost}
  
  【世界观信息】
  世界规模：{world.scale}
  力量体系类型：{world.power_system_type}
  势力格局：{world.factions}
  
  【题材参考】
  核心卖点：{genre_core_selling_points}
  创意约束：{genre_creative_constraints}
  故事规则：{genre_story_rules}
  
  【反套路规则库】
  {anti_trope_rules}
  
  【生成要求】
  为这个项目生成3套创意约束包，每套包含：
  1. package_name: 方案名称（简洁有力）
  2. one_liner_selling_point: 一句话卖点（必须能一句话讲清且不撞模板）
  3. anti_trope_rule: 反套路规则1条（与常规题材写法形成反差）
  4. hard_constraints: 硬约束2-3条（必须遵守的硬性规则，增加故事张力）
  5. protagonist_flaw_driven: 主角缺陷驱动一句话（缺陷如何导致主角付出代价）
  6. antagonist_mirror: 反派镜像一句话（反派与主角的镜像关系）
  7. opening_hook: 开篇钩子（吸引读者继续阅读的开篇设计）
  8. differentiation: 差异化说明（与同类作品的区别）
  9. scoring: 五维评分（每项1-10分，含理由）：
     - creativity: 创意独特性
     - feasibility: 落地可行性
     - market_appeal: 市场吸引力
     - sustainability: 长线可持续性
     - emotional_impact: 情感冲击力
  
  【三问筛选】
  每套方案必须回答：
  1. 为什么这题材必须这么写？
  2. 换常规主角会不会塌？
  3. 卖点能否一句话讲清且不撞模板？
  
  请以JSON格式输出，包含constraint_packages数组。
---