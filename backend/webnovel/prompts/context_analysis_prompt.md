---
system_prompt: 你是一位小说创作的上下文管理专家。你的任务是为当前创作步骤选择最相关的参考信息。输出严格的JSON格式。
user_prompt: |
  {task_context_line}

  【步骤任务】
  {step_description}
  重点关注：{focus}

  【资源目录】
  以下列出本步骤可选的参考资源（含候选条目与可选深度）。请根据任务需要选择最相关的条目：
  {resource_catalog}

  【RAG候选】（预检索结果，仅含正文细节与创作知识；设定类已由【资源目录】结构化资源提供，故不在 RAG 候选内。若与需求高度相关可减少查询数量）
  {rag_candidates_text}

  {prev_step_selections_text}

  {selection_constraints_text}

  {dimension_checklist_text}

  【RAG查询要求】
  - 每条 rag_query 必须是具体的语义检索语句，格式为「核心实体（角色名/地点/物品/组织）+ 关系或事件 + 状态/场景限定」，例如「李承言对张大牛敌意的应对」「林若兮追查密道线索的进展」，而不是「团队内部矛盾」这类泛化短语
  - 禁止原样复制关键事件、章节规划或剧情节点的原文短句（如「争吵爆发；冷静讨论；达成共识」）
  - 每条查询只聚焦一个主题，不同查询覆盖不同主题，避免相互重叠
  - 一般 1~3 条；若【RAG候选】清单已含与需求高度相关的条目，可减少查询数量，优先依赖候选
  - types 选择指引（RAG 仅支持正文细节与创作知识两类）：
    chapter_paragraph（对话/动作/场景细节原文）、chapter_summary（章节梗概）、chapter（机械摘要回退）
    设定类（角色/世界观/力量体系/金手指/卷纲/反派/伏笔）已由【资源目录】结构化资源提供，禁止生成这些类型的 rag_query
  - limit 建议：chapter_paragraph 取 5~8，chapter_summary/chapter 取 3~5

  查询示例（好 vs 坏）：
  - 好：{{"text": "李承言对张大牛敌意的应对", "types": ["chapter_paragraph"], "limit": 5}}
  - 好：{{"text": "林若兮追查密道线索的进展", "types": ["chapter_paragraph"], "limit": 5}}
  - 好：{{"text": "王芳调解团队矛盾的言行", "types": ["chapter_paragraph"], "limit": 5}}（角色行为细节从正文段落检索）
  - 坏：{{"text": "团队内部矛盾", "types": ["chapter_paragraph"], "limit": 5}}（无实体，检索命中差）
  - 坏：{{"text": "争吵爆发；冷静讨论；达成共识", "types": ["chapter_paragraph"], "limit": 5}}（复制原文，禁止）

  【输出格式】
  请严格按以下 JSON 格式输出选择指令，直接输出JSON不要包含其他内容：
  {output_schema}
---
