---
system_prompt: 你是一位小说创作的上下文管理专家。你的任务是为当前创作步骤选择最相关的参考信息。输出严格的JSON格式。
user_prompt: |
  {task_context_line}

  【步骤任务】
  {step_description}
  重点关注：{focus}

  【资源目录】
  以下仅列出本步骤的重要/热点参考信息（写作锚点），条目编号即引用键：structured_refs 的 ids 直接使用目录条目编号，previous_chapter 使用目录中的第N章章节号。目录未列出的数据（其他角色、历史章节、历史伏笔、角色关系、成长弧、剧情点、卷纲等）一律通过 structured_queries 按条件查询获取：
  {resource_catalog}

  【RAG候选】
  {rag_candidates_text}

  {prev_step_selections_text}

  {selection_constraints_text}

  {dimension_checklist_text}

  【结构化查询要求】
  - structured_queries 用于从业务库动态检索结构化数据（角色卡/角色状态/伏笔/时间轴/角色物品/角色关系/成长弧/剧情点/规划/卷纲/章节结尾/爽点/反派/剧情线/世界观历史/世界观设定/设定变更/章节时间轴/金手指动态/境界明细等），当【资源目录】未列出所需条目、或需按条件筛选时使用
  - resource 只能取本节点【可查询资源】中的类型；filters 仅支持该资源的过滤条件字段，未知字段无效
  - **过滤优先用角色名/卷名/场景名等自然标识（模糊匹配即可），id 仅当你确知时使用**
  - 能通过 structured_refs 精确选择的优先用 structured_refs；structured_queries 用于目录之外的全量/筛选检索，一般 0~3 条
  - text 简述查询意图（供追溯），limit 控制在合理条数（默认 5）

  【RAG查询要求】
  - 每条 rag_query 必须是具体的语义检索语句，格式为「核心实体（角色名/地点/物品/组织）+ 关系或事件 + 状态/场景限定」，例如「李承言对张大牛敌意的应对」「林若兮追查密道线索的进展」，而不是「团队内部矛盾」这类泛化短语
  - 禁止原样复制关键事件、章节规划或剧情节点的原文短句（如「争吵爆发；冷静讨论；达成共识」）
  - 每条查询只聚焦一个主题，不同查询覆盖不同主题，避免相互重叠
  - 一般 1~3 条；若【RAG候选】清单已含与需求高度相关的条目，可减少查询数量，优先依赖候选
  - types 选择指引（RAG 仅支持正文细节与创作知识两类）：
    chapter_paragraph（对话/动作/场景细节原文）、chapter_summary（章节梗概）、chapter（机械摘要回退）
    设定类（角色/世界观/力量体系/金手指/卷纲/反派/伏笔）已由【资源目录】结构化资源提供，禁止生成这些类型的 rag_query
  - limit 建议：chapter_paragraph 取 5~8，chapter_summary/chapter 取 3~5

  【输出格式】
  请严格按以下 JSON 格式输出选择指令，直接输出JSON不要包含其他内容：
  {output_schema}
---
