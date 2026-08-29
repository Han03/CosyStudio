---
system_prompt: 你是一位专业的网文金手指设计师，擅长基于已确定的金手指方向展开完整详细设定，包括成长升级路线、爽点嵌入设计和读者反馈节奏
user_prompt: |
  以下网文项目已经确定了金手指的基本方向（来自用户在初始化表单中的选择），请基于该方向展开完整、详细的金手指设定。

  【项目信息】
  书名：{project.title}
  题材：{project.genre_label}
  一句话故事：{project.one_liner}
  故事梗概：{project.story_summary}
  核心冲突：{project.core_conflict}
  目标章节数：{project.target_chapters}
  反套路规则：{project.anti_trope_rules}
  硬性约束：{project.hard_constraints}

  【主角信息】
  姓名：{protagonist.name}
  欲望：{protagonist.desire}
  缺陷：{protagonist.flaw}

  【已确定的金手指方向（用户选择，必须严格保持一致，不得更换方向）】
  金手指类型：{golden_finger.type}
  金手指名称：{golden_finger.name}
  风格：{golden_finger.style}
  可见度：{golden_finger.visibility}
  不可逆代价：{golden_finger.irreversible_cost}

  【题材金手指设计参考】
  {genre_golden_finger_guidelines}

  【设计要求】
  1. 围绕已确定的金手指方向，补全全部详细设定字段；若用户未填写某基本字段（值为空），由你设计填充
  2. upgrade_path 升级路线：设计4-6个递进阶段，覆盖从开局到结局的成长曲线，每个阶段包含阶段名（stage）和该阶段解锁的能力/形态描述（description）
  3. payoff_points 爽点设计：设计4-6个与金手指强绑定的爽点，type 从以下取值中选择（打脸/逆转/升级突破/装逼/复仇/阴谋揭露/战斗高潮/感情），并描述该爽点如何通过金手指实现（description）
  4. feedback_nodes 反馈节奏：设计3-5个周期性反馈机制，type 为反馈类型（如实力展示/代价触发/能力解锁/路人震惊/反派忌惮），chapter_interval 为正整数（表示每隔多少章触发一次），description 描述具体表现形式
  5. 所有设定必须服从反套路规则和硬性约束，并与主角缺陷形成互动（主角缺陷如何影响金手指的使用或代价）

  【输出格式】严格输出JSON格式，不要输出任何其他内容：
  {{
    "type": "金手指类型（与已确定方向一致）",
    "name": "金手指名称（与已确定方向一致）",
    "style": "风格（辅助型/战斗型/经营型/信息流）",
    "visibility": "可见度（隐藏/半透明/公开）",
    "genre_fit": "题材契合度分析",
    "core_function": "核心功能描述",
    "visual_expression": "视觉表现描述",
    "trigger_condition": "触发条件",
    "acquisition_event": "获取事件（金手指如何被主角获得）",
    "growth_rhythm": "成长节奏总述",
    "irreversible_cost": "不可逆代价（与已确定方向一致）",
    "cooldown_limit": "冷却与使用限制",
    "forbidden_items": "禁忌事项",
    "failure_penalty": "失败惩罚",
    "counter_method": "克制方法（敌人如何反制）",
    "anti_trope_alignment": "与反套路规则的契合说明",
    "hard_constraint_binding": "与硬性约束的绑定说明",
    "protagonist_flaw_effect": "主角缺陷对金手指的影响",
    "upgrade_path": [
      {{"stage": "阶段名", "description": "该阶段解锁的能力/形态"}}
    ],
    "payoff_points": [
      {{"type": "爽点类型", "description": "爽点如何通过金手指实现"}}
    ],
    "feedback_nodes": [
      {{"type": "反馈类型", "chapter_interval": 5, "description": "具体表现形式"}}
    ]
  }}
---
