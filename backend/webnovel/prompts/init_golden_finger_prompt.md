---
system_prompt: 你是一位专业的网文金手指设计师。
user_prompt: |
  请为以下网文项目设计3套不同的金手指方案。

  【项目信息】
  书名：{project_title}
  题材：{genre}
  一句话故事：{one_liner}
  核心冲突：{core_conflict}
  主角姓名：{protagonist_name}
  主角欲望：{protagonist_desire}
  主角缺陷：{protagonist_flaw}

  【用户已填金手指信息】
  金手指类型：{gf_type}
  金手指名称：{gf_name}
  金手指风格：{gf_style}
  可见度：{gf_visibility}
  不可逆代价：{gf_irreversible_cost}

  【生成要求】
  生成3套差异化的金手指方案，每套包含：
  1. option_name: 方案名称（如"系统流金手指"、"传承型金手指"、"无金手指纯实力"）
  2. type: 金手指类型（无金手指/系统/传承/法宝/血脉/功法/重生/其他）
  3. name: 金手指名称
  4. style: 风格（辅助型/战斗型/经营型/信息流）
  5. visibility: 可见度（隐藏/半透明/公开）
  6. irreversible_cost: 不可逆代价
  7. growth_rhythm: 成长节奏
  8. scoring: 五维评分（每项1-10分，含理由）

  注意：如果用户已填写某个字段，至少有一套方案应保留用户输入；其他方案可提供不同方向。

  【输出格式】JSON格式，包含options数组。每套方案必须包含scoring字段，示例：
  {{
    "options": [
      {{
        "option_name": "xxx",
        "type": "系统",
        "name": "xxx",
        "style": "辅助型",
        "visibility": "隐藏",
        "irreversible_cost": "xxx",
        "growth_rhythm": "xxx",
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
