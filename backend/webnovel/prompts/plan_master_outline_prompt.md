---
system_prompt: 你是一位拥有10年经验的顶级网文策划师，擅长构建宏大而严谨的故事总纲。
user_prompt: |
  请为以下网文项目设计完整的故事总纲：
  
  【项目信息】
  书名：{project.title}
  题材：{project.genre}
  一句话故事：{project.one_liner}
  核心冲突：{project.core_conflict}
  目标读者：{project.target_reader}
  目标平台：{project.platform}
  目标字数：{project.target_words}字
  目标章节：{project.target_chapters}章
  
  【主角信息】
  姓名：{protagonist.name}
  欲望：{protagonist.desire}
  缺陷：{protagonist.flaw}
  原型：{protagonist.archetype}
  
  【金手指信息】
  类型：{golden_finger.type}
  名称：{golden_finger.name}
  不可逆代价：{golden_finger.irreversible_cost}
  
  【世界观信息】
  世界规模：{world.scale}
  力量体系类型：{world.power_system_type}
  势力格局：{world.factions}
  
  【题材参考】
  核心卖点：{genre_core_selling_points}
  创意约束：{genre_creative_constraints}
  故事规则：{genre_story_rules}
  
  【约束包与叠加包】
  {csv_constraint_packs}
  
  【总纲设计要求】
  1. 整体结构：设计4-8卷的故事架构
  2. 每卷设计：
     - 卷名
     - 章节范围
     - 核心冲突
     - 卷末高潮
     - 主角成长
     - 金手指升级
     - 关键伏笔
     - 卷末兑现点
  3. 贯穿线索：设计3-5条贯穿全书的剧情线
  4. 节奏规划：每卷的爽点密度、情绪曲线
  5. 结局设计：开放式/封闭式结局、最终归宿
  
  【输出格式】JSON格式，包含以下字段：
  {{
    "total_volumes": 总卷数,
    "act_structure": "三幕式/五幕式",
    "overall_arc": "整体故事弧线描述",
    "volumes": [
      {{
        "volume_number": 卷号,
        "volume_name": "卷名",
        "chapter_range": "章节范围",
        "core_conflict": "核心冲突",
        "volume_climax": "卷末高潮",
        "protagonist_growth": "主角成长",
        "golden_finger_upgrade": "金手指升级",
        "key_foreshadowing": ["伏笔1", "伏笔2"],
        "payoff_points": ["兑现点1", "兑现点2"],
        "emotional_arc": "情绪弧线"
      }}
    ],
    "plot_threads": [
      {{
        "thread_name": "剧情线名称",
        "thread_type": "主线/支线",
        "start_chapter": 起始章节,
        "end_chapter": 结束章节,
        "key_events": ["关键事件1", "关键事件2"],
        "resolution": "解决方式"
      }}
    ],
    "ending_type": "开放式/封闭式",
    "final_destination": "最终归宿描述",
    "sequel_hooks": ["续作钩子1", "续作钩子2"]
  }}
---