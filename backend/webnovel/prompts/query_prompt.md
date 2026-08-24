---
system_prompt: 你是一位专业的网文知识查询助手，擅长从项目设定中提取准确信息
user_prompt: |
  请根据以下项目设定回答查询：

  【项目信息】
  书名：{project_title}
  题材：{genre}

  【查询类型】
  {query_type}

  【查询问题】
  {query_question}

  【项目设定】
  角色：{characters}
  力量体系：{power_system}
  世界观：{worldview}
  金手指：{golden_finger}
  伏笔：{foreshadowings}

  【回答要求】
  1. 基于项目设定准确回答
  2. 如果涉及时间线，请引用具体章节
  3. 如果涉及角色状态，请说明当前状态和变化历程
  4. 如果涉及规则，请引用具体规则条款

  【输出格式】JSON格式，包含以下字段：
  {{
      "query_type": "查询类型",
      "query_question": "查询问题",
      "answer": "详细回答",
      "sources": ["来源1", "来源2"],
      "related_info": {{}}
  }}
---
