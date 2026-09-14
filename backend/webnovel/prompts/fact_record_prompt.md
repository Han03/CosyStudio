---
system_prompt: 你是一位专业的内容分析助手，擅长提取文本中的关键信息，输出严格的JSON格式
user_prompt: |
  请从以下章节内容中提取关键信息：

  重要：必须提取所有对后续剧情有影响的核心事件，包括但不限于角色升级突破、重要物品获得/消耗/失去、角色关系变化、身份揭露、能力提升。不要遗漏任何改变角色状态的事件；各事件分别归入下方对应结构化块（character_updates / item_changes / open_loops / cool_points），不要遗漏。

  【章节内容】
  {chapter_content}

  【已知设定】
  世界观: {world_settings}
  角色: {characters}

  【角色更新 character_updates】当章节中出现影响角色卡的关键变化时提取，每类一条，character/target 必须与【角色】清单一致，无法匹配清单角色的不要提取：
  - type 枚举：关系 | 身份揭露 | 成长 | 能力
  - 关系：角色间关系变化（character=角色A, target=角色B, description=变化说明），如 {{"type": "关系", "character": "李威", "target": "苏婉清", "description": "因路线选择产生激烈冲突，最终因林若兮的调解妥协"}}
  - 身份揭露：化名/曾用名角色的真实身份揭晓（alias=曾用名或化名, real_name=真名, description=身份说明），如 {{"type": "身份揭露", "alias": "神秘黑袍男人", "real_name": "李岩", "description": "总兵府护卫统领"}}；未揭露真实姓名的不要提取
  - 成长：角色升级/突破/成长（character=角色名, description=成长说明）
  - 能力：角色获得/提升能力或技能（character=角色名, ability=能力名, description=能力说明）

  【物品变化 item_changes】当角色获得、失去、消耗、损毁或赠出对剧情有意义的物品（武器、钱财、关键道具等）时提取，每件物品一条，禁止用顿号/逗号并列多个物品：
  - character: 角色名（与【角色】清单一致）
  - action: 仅限 "获得" 或 "失去"（获得=得到/缴获/买下/拾得/收下等；失去=丢失/损毁/赠予/交出/被夺/花掉/花费/消耗/用掉/付给等，消耗与花费统一用"失去"）
  - item: 纯物品名，禁止带数字与单位（如"银子"，不要写"8两银子"；数量写进 quantity，单位与原文写进 note）
  - quantity: 数量整数 >=1，获得与失去都必填（"8两银子" → quantity=8）；失去时显式 0 表示全部失去；不填默认 1
  - note: 变化说明（保留原文，如"从流民处搜得8两"、"客栈食宿花费5两"）
  
  【伏笔 open_loops】本章新埋下的伏笔（不要提取已在前面章节交代过的物品、设定或事件作为新伏笔）：
  - content: 伏笔内容描述
  - tier: 核心/支线/装饰（核心伏笔回收周期50-300章，支线30-100章，装饰10-30章）
  - target_chapter: 预计回收章节（0表示未定）
  - evidence: 原文证据片段

  【爽点 cool_points】本章让读者感到爽快、满足的情节：
  - content: 爽点内容描述
  - cool_point_type: 装逼打脸/扮猪吃虎/越级反杀/打脸权威/反派翻车/甜蜜超预期/突破/升级/寻宝/奇遇/逆袭/情感/解谜/反转/发现
  - execution_mode: 装逼打脸/扮猪吃虎/越级反杀/打脸权威/反派翻车/甜蜜超预期
  - structure_stage: 铺垫/爆发/释放（铺垫=制造压力悬念，爆发=展示实力反击，释放=读者满足）
  - pressure_level: 1-10（铺垫阶段压力强度）
  - release_level: 1-10（释放阶段爽感强度）
  - reader_emotion: 读者预期情感反应
  - impact_score: 1-10（影响评分）
  - evidence: 原文证据片段

  【结尾钩子 hook】从章节内容末尾提取结尾留下的故事状态与未了线索（若结尾安静收束、无明显悬念，不要强行提取）：
  - hook_content: 结尾故事状态/未了线索描述
  - hook_type: 悬念式/冲突式/反转型/情感式/安静收束
  - hook_strength: 强/中/弱
  - hook_pattern: 结尾手法（如：悬念留白/矛盾激化/信息差/反转/情绪落点）
  - ending_emotion: 期待/紧张/感动/愤怒/平静
  - ending_time: 场景时间（如：白天/夜晚/黄昏/清晨）
  - ending_location: 场景地点

  【角色状态 character_states】提取各主要角色在本章【结束时】的状态快照（仅限正文中实际出场的角色，每角色一条）：
  - character_id: 角色ID（对应【角色】清单中的 id）
  - character_name: 角色名
  - location: 章末所在位置
  - state_summary: 章末身体/处境状态（受伤/体力/得失/异常），用一句话概括
  - emotion: 章末情绪
  - knowledge: 本章新获得的信息与认知（无则空字符串）
  - notes: 其他关键状态变化（无则空字符串）

  【输出格式】
  请严格按照JSON格式输出，只输出JSON，不要包含任何其他内容：
  {{"item_changes": [{{"character": "角色名", "action": "获得|失去", "item": "物品名", "quantity": 1, "note": "说明"}}], "character_updates": [{{"type": "关系|身份揭露|成长|能力", "character": "角色名", "target": "关联角色", "alias": "曾用名", "real_name": "真名", "ability": "能力名", "description": "说明"}}], "open_loops": [{{"content": "伏笔内容", "tier": "核心/支线/装饰", "target_chapter": 0, "evidence": "证据"}}], "cool_points": [{{"content": "爽点内容", "cool_point_type": "类型", "execution_mode": "模式", "structure_stage": "铺垫/爆发/释放", "pressure_level": 1, "release_level": 1, "reader_emotion": "情感", "impact_score": 1, "evidence": "证据"}}], "hook": {{"hook_content": "结尾状态", "hook_type": "类型", "hook_strength": "强/中/弱", "hook_pattern": "手法", "ending_emotion": "情感", "ending_time": "时间", "ending_location": "地点"}}, "character_states": [{{"character_id": 1, "character_name": "角色名", "location": "位置", "state_summary": "状态", "emotion": "情绪", "knowledge": "认知", "notes": "备注"}}]}}
  open_loops/cool_points/character_states/item_changes/character_updates 无内容时输出空数组，hook 无内容时输出空对象。
---
