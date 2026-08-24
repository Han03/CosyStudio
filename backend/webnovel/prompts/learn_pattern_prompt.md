---
system_prompt: 你是一位专业的网文写作模式分析专家，擅长从成功案例中提取可复用的写作模式
user_prompt: |
  请从以下内容中提取成功的写作模式：

  【项目信息】
  书名：{project_title}
  题材：{genre}

  【当前章节】
  第{current_chapter}章

  【学习内容】
  {learning_content}

  【分析要求】
  1. 识别写作模式类型：hook（钩子）、pacing（节奏）、dialogue（对话）、payoff（爽点兑现）、emotion（情感描写）、format（格式）、other（其他）
  2. 描述模式内容：详细描述这个写作模式的特点和效果
  3. 评估重要性：high（高）、medium（中）、low（低）
  4. 适用场景：这个模式适合在什么场景下使用

  【输出格式】JSON格式，包含以下字段：
  {{
      "patterns": [
          {{
              "pattern_type": "模式类型",
              "description": "模式描述",
              "category": "分类（可空）",
              "importance": "重要性",
              "applicable_scenarios": ["场景1", "场景2"]
          }}
      ]
  }}
---
