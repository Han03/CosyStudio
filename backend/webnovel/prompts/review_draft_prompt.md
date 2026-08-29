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

  注意：该草稿是白描骨架稿，环境渲染、心理描写、文笔细节将由后续润色阶段补全，
  审查时不要因“描写不够细腻”扣分，请聚焦剧情结构、设定一致性、爽点布局、叙事连贯性等骨架质量。
  不要因“结尾缺少明显钩子/悬念”扣分，自然收尾是正确的收尾；设问收束、预告式旁白、总结预言等公式化悬念才是问题。
  8分以上表示骨架质量优秀，请严格按标准评分，不要普遍给高分。

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
