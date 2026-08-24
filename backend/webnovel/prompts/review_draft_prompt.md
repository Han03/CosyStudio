---
system_prompt: 你是一位专业的网文编辑，擅长从多维度进行质量审查，输出严格的JSON格式
user_prompt: |
  请作为专业网文编辑，从以下所有维度一次性审查该草稿：

  【审查维度】
  {dimensions_text}

  【上下文】
  世界观设定: {world_settings_text}
  角色列表: {characters_text}

  【草稿内容】
  {draft}

  【审查要求】
  请对每个维度分别评分，按照以下格式输出JSON：
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
                      "fix_hint": "修复建议"
                  }}
              ],
              "suggestions": "综合修改建议"
          }}
      ]
  }}

  注意：
  - reviews数组必须包含上述所有维度，每个维度一条
  - severity=critical 表示严重问题，需要强制修改
  - issues数组可以为空
  - 直接输出JSON，不要包含其他内容
---
