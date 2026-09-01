---
system_prompt: 你是一位拥有10年经验的顶级网文编辑和创意策划师，擅长为网文项目进行全方位的故事定位、角色设计、金手指设计、世界观构建和创意约束规划。你需要一次性生成3套完整的、差异化的网文项目方案。
user_prompt: |
  请为以下网文项目一次性生成3套完整的设定方案。每套方案必须包含故事核与商业定位、角色骨架、金手指、世界观、创意约束包全部5个维度的完整设定。

  【已知信息】
  书名：{title}
  用户选择题材：{genre_display}

  【用户已填信息】
  一句话故事：{one_liner_display}
  核心冲突：{core_conflict_display}

  【题材约束】
  genre 字段必须严格从以下系统支持的题材中选择，不得自创：{genre_list_str}
  如果用户已选择题材，至少有一套方案应使用该题材；其他方案可以推荐更适合的不同题材。

  【生成要求】
  生成3套差异化的完整方案（如"商业燃文路线"、"深度剧情路线"、"创新实验路线"），每套包含以下全部字段：

  一、故事核与商业定位（project）
  1. genre: 最匹配的题材（必须从上述题材列表中选择）
  2. one_liner: 一句话故事（必须能一句话讲清且不撞模板，禁止出现任何人名）
  3. core_conflict: 核心冲突（禁止出现人名）
  4. target_words: 目标字数（数字）
  5. target_chapters: 目标章节（数字）
  6. target_reader: 目标读者（禁止出现人名）
  7. platform: 目标平台

  二、角色骨架与关系冲突（protagonist）
  1. name: 主角姓名——必须是一个具体人物的姓名（2-4个汉字），禁止使用家族名、势力名、群体称谓
  2. archetype: 主角原型（如：废柴逆袭、重生归来）
  3. desire: 主角欲望（最想要的是什么）
  4. flaw: 主角缺陷（会导致主角付出代价的缺陷）
  5. structure: 主角结构（单主角/多主角）
  6. villain_mirror: 反派镜像一句话（反派与主角的镜像关系）
  7. heroine_config: 感情线配置（无女主/单女主/多女主）
  8. antagonist_level: 反派分层（BOSS级/多级反派）

  三、金手指与兑现机制（golden_finger）
  1. type: 金手指类型（无金手指/系统/传承/法宝/血脉/功法/重生/其他）
  2. name: 金手指名称
  3. style: 风格（辅助型/战斗型/经营型/信息型）
  4. visibility: 可见度（隐藏/半公开/公开）
  5. irreversible_cost: 不可逆代价（使用金手指必须付出的不可逆代价；若无金手指需说明理由）

  四、世界观与力量规则（world）
  1. scale: 世界规模（单城/多城/大陆/多界）
  2. power_system_type: 力量体系类型（修仙/武道/魔法/科技/异能/职场/无）
  3. factions: 势力格局
  4. social_class: 社会阶层与资源分配
  5. currency_system: 货币体系
  6. cultivation_chain: 境界链（如适用）
  7. sect_hierarchy: 宗门/组织层级（如适用）

  五、创意约束包（constraints）
  1. anti_trope_rule: 反套路规则1条（与常规题材写法形成反差）
  2. hard_constraints: 硬约束2-3条（必须遵守的硬性规则，增加故事张力）
  3. core_selling_points: 核心卖点（一句话讲清本书的独特卖点）
  4. opening_hook: 开篇钩子（吸引读者继续阅读的开篇设计）

  六、整体评分（scoring）
  五维评分（每项1-10分，含理由）：
  - creativity: 创意独特性
  - feasibility: 落地可行性
  - market_appeal: 市场吸引力
  - sustainability: 长线可持续性
  - emotional_impact: 情感冲击力

  【重要约束】
  1. one_liner、core_conflict、target_reader 等字段中禁止出现任何人名
  2. 3套方案之间必须有显著差异化（不同题材方向、不同角色类型、不同金手指设计、不同世界观）
  3. 每套方案内部必须逻辑自洽（题材-角色-金手指-世界观-约束包风格统一）

  【输出格式】JSON格式，包含sets数组。示例：
  {{
    "sets": [
      {{
        "set_name": "方案A：xxx",
        "project": {{
          "genre": "{example_genre}",
          "one_liner": "xxx",
          "core_conflict": "xxx",
          "target_words": 1000000,
          "target_chapters": 200,
          "target_reader": "xxx",
          "platform": "xxx"
        }},
        "protagonist": {{
          "name": "xxx",
          "archetype": "xxx",
          "desire": "xxx",
          "flaw": "xxx",
          "structure": "单主角",
          "villain_mirror": "xxx",
          "heroine_config": "无女主",
          "antagonist_level": "BOSS级"
        }},
        "golden_finger": {{
          "type": "系统",
          "name": "xxx",
          "style": "辅助型",
          "visibility": "隐藏",
          "irreversible_cost": "xxx"
        }},
        "world": {{
          "scale": "大陆",
          "power_system_type": "修仙",
          "factions": "xxx",
          "social_class": "xxx",
          "currency_system": "xxx",
          "cultivation_chain": "xxx",
          "sect_hierarchy": "xxx"
        }},
        "constraints": {{
          "anti_trope_rule": "xxx",
          "hard_constraints": ["xxx", "xxx"],
          "core_selling_points": "xxx",
          "opening_hook": "xxx"
        }},
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
