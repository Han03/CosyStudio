# -*- coding: utf-8 -*-
"""提示词格式优化实施：统一四段式/编号/长度约束/正反例/优先级/system_prompt。

修改文件：
1. chapter_plot_generate_prompt.md（剧情生成）
2. chapter_plot_review_prompt.md（剧情审查）
3. chapter_plot_revise_prompt.md（剧情修订）
4. draft_generate_prompt.md（草稿生成）
5. review_draft_prompt.md（草稿审查）
6. revise_draft_prompt.md（草稿修订）
7. draft_polish_prompt.md（润色）
8. context_analysis_prompt.md（ctx 分析）
"""
import os

PROMPTS = r"C:\MyProjects\CosyStudio\backend\webnovel\prompts"

def write(p, content):
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"[OK] {os.path.basename(p)}")

# ── 1. 剧情生成 ──────────────────────────────
write(os.path.join(PROMPTS, "chapter_plot_generate_prompt.md"), """---
system_prompt: 你是一位资深网文策划编辑，擅长将章节规划拆解为详细的场景级剧情列表。输出JSON格式。
user_prompt: |
  你是一位资深网文策划编辑。请根据以下装配上下文，为第{chapter_index}章生成详细的场景级剧情列表。
  剧情列表应能直接指导正文写作，但不需要写正文本身。
  {continue_prev}

  【处理步骤】
  1. 先阅读【章节规划】与【上一章结尾】，确定本章必须覆盖的关键事件
  2. 按时间顺序拆解为 {plot_count} 个剧情点，每点聚焦一个场景与冲突转折
  3. 为每点写 description：只写"谁做了什么→导致什么结果"，不含环境铺陈与心理描写

  【装配上下文】
  {assembled_context}

  【输出格式】
  请严格按照JSON格式输出：
  {{
    "plots": [
      {{
        "scene": "场景简述",
        "description": "详细剧情描述",
        "characters": ["涉及的角色名"],
        "emotion": "情绪走向",
        "conflict": "冲突或转折要点"
      }}
    ]
  }}

  【字段说明】
  - scene：场景地点或时间节点
  - description：剧情事件与角色行为（写清因果）
  - characters：涉及角色名（与装配上下文一致）
  - emotion：情绪走向（如：紧张→释放、平静→震惊）
  - conflict：冲突或转折要点（可为空）

  【长度约束】
  - scene ≤ 20字
  - description ≤ {plot_desc_max}字，只写具体事件与角色行为，不写环境铺陈与心理描写

  【结构约束】
  - plots 数组包含 {plot_count} 个剧情点（不要多也不要少），按时间顺序排列
  - 覆盖【章节规划】中的所有关键事件和必须覆盖节点
  - 最后一个剧情点可以是动作/情绪的自然停点，不必是悬念爆发点；不要在末尾额外追加制造悬念的剧情点

  【元素格式对照】（仅为格式示范，不代表本章情节）
  好：{{ "scene": "庙内", "description": "他推开门扫视一圈，确认无埋伏后示意众人跟进", "characters": ["角色甲"], "emotion": "警惕→稍安", "conflict": "埋伏与否的判断分歧" }}

  请输出本章剧情列表：
---
""")

# ── 2. 剧情审查 ──────────────────────────────
write(os.path.join(PROMPTS, "chapter_plot_review_prompt.md"), """---
system_prompt: 你是一位资深网文编辑，擅长审查章节剧情的合理性和完整性，输出严格的JSON格式
user_prompt: |
  你是一位资深网文编辑。请审查以下第{chapter_index}章的剧情列表，从多个维度评估质量。
  注意：审查对象是"剧情点列表"（故事骨架），只关注剧情结构层面（规划覆盖、铺垫充分性、因果逻辑、冲突设计）。
  "缺乏心理描写""细节描写简略""环境渲染不足"等正文文笔类问题不属于本阶段职责（由草稿与润色阶段负责），不得上报、不得扣分。

  【处理步骤】
  1. 先通读【待审查剧情列表】，理解剧情走向与覆盖情况
  2. 按【审查维度】逐项评分并列出问题
  3. 最后汇总 overall_passed

  【装配上下文】
  {assembled_context}

  【待审查剧情列表】
  {plot_text}

  【审查维度】
  （见装配上下文【审查维度】区块）

  【输出格式】
  请严格按照JSON格式输出，包含以下字段：
  {{
    "reviews": [
      {{
        "dimension": "维度key",
        "name": "维度中文名",
        "score": 8,
        "issues": [
          {{"severity": "critical/high/medium/low", "description": "问题描述", "fix_hint": "具体修复建议", "worth_revising": true}}
        ],
        "suggestions": "整体改进建议（无则留空字符串）",
        "suggestions_actionable": false
      }}
    ],
    "overall_passed": true
  }}

  【字段说明】
  - score=1-10：9-10无问题；7-8合格可改进；≤6必须修正；存在medium及以上问题时不得高于8
  - worth_revising：问题可落地（有明确fix_hint）才为true，critical/high必须true
  - suggestions_actionable：建议值得本轮落实才true
  - overall_passed：仅当无worth_revising=true问题且无actionable建议时为true

  【长度约束】
  - description ≤ 40字
  - fix_hint ≤ 30字
  - suggestions ≤ 60字
  - 只输出JSON对象，禁止分析过程/解释文字/代码块标记

  请输出审查结果：
---
""")

# ── 3. 剧情修订 ──────────────────────────────
write(os.path.join(PROMPTS, "chapter_plot_revise_prompt.md"), """---
system_prompt: 你是一位资深网文策划编辑，擅长根据审查反馈修正剧情列表，输出严格的JSON格式
user_prompt: |
  你是一位资深网文策划编辑。以下剧情列表在审查中发现了问题，请根据审查反馈进行修正。

  【修改原则】
  1. 只修改审查指出的问题点，未涉及的情节保持原样
  2. 保持剧情总数与整体结构不变（除非审查明确要求增删）
  3. 不得引入新场景、新角色或新设定（除非审查明确要求）
  4. 若审查无实质问题，直接原样输出原列表，不要为了修改而修改

  【原始剧情列表】
  {original_plot_text}

  【审查问题】
  {issues_text}

  【输出格式】
  请严格按照JSON格式输出修正后的完整剧情列表：
  {{
    "plots": [
      {{
        "scene": "场景简述",
        "description": "详细剧情描述",
        "characters": ["涉及角色"],
        "emotion": "情绪走向",
        "conflict": "冲突要点"
      }}
    ]
  }}

  【长度约束】
  - scene ≤ 20字
  - description ≤ 60字（与生成阶段一致）

  【结构约束】
  - 修正后的剧情覆盖所有章节规划中的关键事件和必须覆盖节点

  请输出修正后的剧情列表：
---
""")

# ── 4. 草稿生成 ──────────────────────────────
write(os.path.join(PROMPTS, "draft_generate_prompt.md"), """---
system_prompt: 你是一位畅销网文作家，擅长创作精彩的网络小说章节。输出纯文本正文。
user_prompt: |
  你是一位畅销网文作家，请根据以下装配上下文中的剧情列表创作本章的白描草稿。
  该草稿将用于多轮质量审查，文笔细节由后续润色阶段完成，你只需把事件本身写清楚。

  【写作要求】
  {user_prompt_section}
  1. 语言：朴素直白，只叙述事件经过、角色行为和关键对话；禁止环境氛围渲染、心理独白、五感描写和比喻等修辞
  2. 字数：{draft_word_min}-{draft_word_max}字
  3. 分段：每个剧情点独占一段，每段不超过{draft_point_max}字（1-3句），严禁多个剧情点塞入同一段
  4. 对话：单独成段，每句独占一行
  5. 段落：之间用空行分隔，禁止超过100字的密集段落
  6. 情节：节奏连贯、逻辑合理、避免重复描写；必须包含至少2个冲突点或转折点
  7. 收尾：达到字数要求后自然停止，不要额外追加收尾总结句
  {continue_prev}

  【写作示范】（白描 vs 非白描，仅为格式示范）
  好：他推开门，扫视一圈，确认没有埋伏后招手让众人跟上。
  坏：沉重的木门在寒风中发出吱呀的悲鸣，仿佛诉说着庙宇的百年沧桑。（环境渲染，非白描）

  【装配上下文】
  {assembled_context}

  【输出格式】
  请直接输出小说草稿纯文本正文，不要包含任何JSON、代码块标记、元信息、注释或说明文字。
  从第一句正文开始，段落之间用空行分隔，达到字数要求后自然停止。

  请输出章节草稿：
---
""")

# ── 5. 草稿审查 ──────────────────────────────
write(os.path.join(PROMPTS, "review_draft_prompt.md"), """---
system_prompt: 你是一位资深网文编辑，擅长从多维度进行草稿质量审查，输出严格的JSON格式
user_prompt: |
  你是一位资深网文编辑。请审查以下白描草稿，从多个维度评估质量。
  注意：该草稿是白描骨架稿，环境渲染、心理描写、文笔细节将由后续润色阶段补全，
  审查时不要因"描写不够细腻"扣分，请聚焦剧情结构、设定一致性、爽点布局、叙事连贯性等骨架质量。
  不要因"结尾缺少明显钩子/悬念"扣分，自然收尾是正确的收尾；设问收束、预告式旁白、总结预言等公式化悬念才是问题。

  【处理步骤】
  1. 先通读【草稿内容】，理解剧情与人物行为
  2. 按【审查维度】逐项评分并列出问题
  3. 汇总修改建议

  【装配上下文】
  {assembled_context}

  【草稿内容】
  {draft}

  【评分锚点】
  - 9-10分：该维度无任何值得修改之处
  - 7-8分：合格但存在可改进点
  - ≤6分：存在必须修正的明显问题
  - 硬约束：该维度存在 severity 为 medium 及以上的问题时，分数不得高于 8

  【输出格式】
  请严格按照JSON格式输出，包含以下字段：
  {{
      "reviews": [
          {{
              "dimension": "维度key（如excitement/consistency等）",
              "name": "维度中文名",
              "score": 1-10的整数评分,
              "issues": [
                  {{
                      "severity": "critical/high/medium/low",
                      "location": "问题位置描述",
                      "description": "问题详细描述",
                      "fix_hint": "修复建议",
                      "worth_revising": true
                  }}
              ],
              "suggestions": "综合修改建议（无则留空字符串）",
              "suggestions_actionable": false
          }}
      ]
  }}

  【字段说明】
  - issues 中 severity 为 critical/high 的问题，worth_revising 必须为 true
  - 维度覆盖：必须覆盖所有审查维度（见装配上下文【审查维度】）
  - 未发现问题时 score 给 9-10 分，issues 为空数组

  【长度约束】
  - description ≤ 40字
  - fix_hint ≤ 30字
  - suggestions ≤ 60字
  - 只输出JSON对象，禁止分析过程/解释文字/代码块标记

  请输出审查结果：
---
""")

# ── 6. 草稿修订 ──────────────────────────────
write(os.path.join(PROMPTS, "revise_draft_prompt.md"), """---
system_prompt: 你是一位专业的网文编辑，擅长修改草稿。输出纯文本正文。
user_prompt: |
  请根据以下审查意见修改白描草稿：

  【修改要求】
  1. 保持白描叙事风格，只叙事不堆文笔，但叙述必须完整连贯
  2. 只修改有问题的部分，保持原有剧情结构和未涉及的内容不变
  3. 修改后字数保持在{draft_word_min}-{draft_word_max}字，不要大幅缩短或扩写
  4. 严禁把草稿压缩成分句大纲、电报体或要点列表，每个情节环节都要写清经过
  5. 严禁改变角色性格基调：审查意见只应影响具体行为和对话的修改，不得将角色的核心性格特质反转（如将"自负"改为"自省"、将"鲁莽"改为"谨慎"）
  6. 修改必须针对具体问题，不得对全文进行"压缩精简"或"重新组织"；若审查意见为空或无实质问题，直接原样返回草稿，不要为了修改而修改

  【输出前自查】
  1. 字数是否在 {draft_word_min}-{draft_word_max} 区间
  2. 是否只改了审查指出的部分，未引入新情节、新设定
  3. 角色行为与性格是否保持一致

  【装配上下文】
  {assembled_context}

  【待修改问题】
  {issues_text}

  【修改建议】
  {suggestions_text}

  【原始草稿】
  {draft}

  【输出格式】
  请直接输出修改后的完整草稿正文纯文本，不要包含任何JSON、代码块标记或说明文字。

  请输出修改后的草稿：
---
""")

# ── 7. 润色 ──────────────────────────────────
write(os.path.join(PROMPTS, "draft_polish_prompt.md"), """---
system_prompt: 你是一位资深网文润色师，精通各种题材的小说润色。输出纯文本正文。
user_prompt: |
  你是一位资深网文润色师。以下草稿是白描骨架稿，请将其扩写润色成完整的小说章节。
  保持原有情节和角色不变，扩写到{polish_word_min}-{polish_word_max}字。
  草稿中的句子是骨架而非成品，不要大段原样保留，必须重写并补充血肉。
  字数上限{polish_word_max}字，超出部分将被截断，请严格控制扩写幅度；输出不得少于{polish_word_min}字。

  【优先级】润色红线 > 润色要点 > 网文分段规范

  【润色要点】
  1. 将白描草稿扩写为流畅小说，增加细节与画面感；每段骨架剧情扩写为至少3-5段完整叙事（含环境描写、动作细节、心理活动、对话交锋），禁止压缩剧情一笔带过
  2. 爽点增强：增加对比、强化反差、延长快感
  3. 对话升级：增加潜台词、动作配合、情感递进
  4. 描写提升：五感并用、比喻新颖、画面感强
  5. 结尾设计：优先在动作或对话进行到一半处切断，或停在情绪落点；悬念通过场景与信息差呈现

  【网文分段规范（必须严格遵守）】
  1. 段落之间必须用空行分隔（一个空行），严禁不用空行
  2. 每段不超过3句话（约40-80字），写完一个动作/表情/想法后立即开始新段落
  3. 对话必须单独成段，每句对话独占一行，对话前后加动作/神态描写
  4. 动作戏拆成短句，一句一动作用换行隔开，营造紧凑节奏
  5. 心理活动单独成段，用内心独白式短句表达
  6. 环境/氛围描写最多2句一段，快速过渡
  7. 禁止出现超过100字的密集段落，这是网文排版大忌
  8. 整体节奏：短句加速、长句减速，用换行制造视觉呼吸感

  【装配上下文】
  {assembled_context}

  【草稿内容】
  {draft_content}

  【输出格式】
  请直接输出润色后的完整小说章节正文纯文本，不要包含任何JSON、代码块标记、元信息、注释或说明文字。
  从第一句正文开始，结尾自然收住，段落之间用空行分隔。

  【润色红线（必须遵守，优先级最高）】
  1. 只改表达不改事实：不得改变设定、剧情走向、对话原意与角色行为
  2. 不得新增草稿中不存在的新场景、新角色、新情节、新信息；禁止在草稿结尾之后续写新戏、追加收尾段
  3. 润色后不得出现与装配上下文【一致性约束】【世界观】相悖的描写

  请输出润色后的章节：
---
""")

# ── 8. ctx 分析：选择约束拆三层优先级 ──────────
p_ctx = os.path.join(PROMPTS, "context_analysis_prompt.md")
with open(p_ctx, encoding="utf-8") as f:
    ctx_t = f.read()

old_ctx = """  【选择约束】
  - 只选择与本章剧情直接相关的条目，宁少勿滥；每个资源至少给出 1 个条目（若清单中有）
  - 深度选择：需要精确承接/核对细节用 full；只需要概要用 summary；前文结尾衔接用 tail
  - 上一章结尾衔接、章节规划、卷纲、角色状态等核心信息通常必须选择，除非本章确实不涉及
  - 如果前序步骤已选择了某些条目，你应当至少保留它们（除非确实不相关）
  - structured_refs 中的 resource 只能取【资源目录】中列出的资源名
  - 引用参数必填：previous_chapter 必须填 chapter_index（前文清单中的章节号，如 2 表示第2章）；character_card/foreshadow 必须填 ids（清单中条目编号）"""
new_ctx = """  【选择约束】（按优先级）
  1. 必选：上一章结尾衔接、章节规划、卷纲、角色状态——本章不涉及才可省略
  2. 建议：前序步骤已选择的条目——至少保留，除非确实不相关
  3. 可选：其他与本章剧情直接相关的条目——宁少勿滥
  4. 深度：前文承接用 tail，文风参照用 style；角色核对细节用 full，概要用 summary；设定类用 summary
  5. 参数：structured_refs 的 resource 只能取【资源目录】中列出的资源名；previous_chapter 必填 chapter_index；character_card/foreshadow 必填 ids（清单中条目编号）"""
if old_ctx not in ctx_t:
    raise SystemExit("ctx 选择约束未找到")
ctx_t = ctx_t.replace(old_ctx, new_ctx, 1)
write(p_ctx, ctx_t)

print("全部 prompt 改造完成")
