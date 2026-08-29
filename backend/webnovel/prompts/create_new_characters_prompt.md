---
system_prompt: 你是一位专业的网文编辑，擅长识别和分析角色。输出严格的JSON格式，只输出JSON，不要附加任何解释。
user_prompt: |
  以下是一段小说正文和已有的全部角色列表。请识别正文中出现但不在已有角色列表中的新角色，并为每个新角色生成角色卡设定。

  重要：不要创建与已有角色同名、谐音或别名的角色，避免重复。
  注意：如果正文中的角色只是用称呼/别名/头衔指代已有角色，不要重复创建。

  【已有角色（禁止重复）】
  {existing_chars}

  【正文内容】
  {content_sample}

  【character_type 分类标准（必须严格遵守）】
  - villain：与主角方对立、制造核心冲突的反派人物
  - supporting：有具体姓名、预计跨多章出场、推动主线或重要人物关系的配角
  - minor：仅短暂出场一次的功能性角色（路人、传令兵、小商贩、无足轻重的打手等）
  拿不准时优先选 minor，宁可低估后续再升级。

  【输出字段说明（键名必须与下列完全一致）】
  所有新角色都必须输出基础字段：
  - name：角色名（具体人名；无名者用"身份+特征"的短称呼，如"持刀猎户"）
  - character_type：villain/supporting/minor 三选一
  - identity：身份（职业、阵营、来历，一句话）
  - core_personality：性格（2-4 个关键词，顿号分隔）
  - core_tags：核心标签（2-3 个关键词，顿号分隔，如"流寇、贪财、持刀"）
  - first_impression：给读者/主角的第一印象（一句话）
  - short_term_goal：当前阶段的短期目标（一句话，基于正文中该角色正在做的事）

  仅当 character_type 为 supporting 或 villain 时，追加输出深化字段（minor 不要输出这些字段）：
  - true_desire：核心欲望（驱动其行动的深层动机，一句话）
  - personality_flaw：性格缺陷（一句话）
  - starting_state：出场时的初始状态（实力/处境，一句话）
  - long_term_goal：长期目标（一句话；正文明示或可合理推断，推断不出则输出空字符串）
  - behavior_pattern：行为模式（惯常的行事风格，一句话）
  - ability_limit：能力上限（已知最强的能力/手段，一句话；未知则输出空字符串）

  禁止事项：禁止输出字段清单以外的键；禁止编造正文完全没有依据的具体数值（如精确年龄、境界名称）。

  【输出格式】
  请严格按照JSON格式输出，只输出JSON：
  {{"new_characters": [{{"name": "角色名", "character_type": "villain", "identity": "身份", "core_personality": "性格", "core_tags": "标签1、标签2", "first_impression": "第一印象", "short_term_goal": "短期目标", "true_desire": "核心欲望", "personality_flaw": "性格缺陷", "starting_state": "初始状态", "long_term_goal": "长期目标", "behavior_pattern": "行为模式", "ability_limit": "能力上限"}}]}}
  如果没有新角色，输出 {{"new_characters": []}}
---
