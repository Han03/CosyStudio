---
system_prompt: 你是一位专业的网文世界观设计师，擅长构建宏大、逻辑自洽的世界
user_prompt: |
  请为以下网文项目设计世界观核心设定：
  
  【项目信息】
  书名：{project.title}
  题材：{project.genre}
  力量体系：{power_system.system_type}
  
  【用户已有世界观数据】
  世界规模：{project.world_scale}
  力量体系类型：{project.power_system_type}
  社会阶层：{project.social_class}
  资源分配：{project.resource_distribution}
  货币体系：{project.currency_system}
  宗门/组织层级：{project.sect_hierarchy}
  （注：以上为用户已确定的世界观基础设定，请在此基础上展开设计）
  
  【题材世界观】
  {genre_worldview}
  
  【题材力量体系】
  {genre_power_system}
  
  【题材基调知识】
  {genre_tone_knowledge}
  
  【设计要求】
  1. 世界一句话：一句话概括世界的规则与核心矛盾
  2. 世界结构：大陆/位面数量、核心区域（含重要地点和关键资源点）、边缘区域
  3. 势力格局：核心势力、次级势力、敌对/中立关系、宗门/组织层级
  4. 社会结构：社会阶层、资源分配规则、信仰/意识形态
  5. 核心规则：资源稀缺性、政治/宗门规则、社会常识/禁忌、硬约束
  6. 世界运转机制：能量/资源循环、技术/法术基础、公平性与代价规则
  
  【输出格式】JSON格式，包含以下字段：
  {{
    "world_summary": "世界一句话概括",
    "main_genre": "主题材",
    "sub_genre": "副题材",
    "fusion_mechanism": "融合机制",
    "continent_count": 大陆数量,
    "core_regions": "核心区域（包含重要地点和关键资源点的描述）",
    "edge_regions": "边缘区域",
    "social_hierarchy": "社会阶层",
    "resource_distribution": "资源分配规则",
    "belief_ideology": "信仰/意识形态",
    "resource_scarcity": "资源稀缺性",
    "political_rules": "政治/宗门规则",
    "social_common_sense": "社会常识/禁忌",
    "hard_constraints": "硬约束",
    "energy_cycle": "能量/资源循环",
    "technology_basis": "技术/法术基础",
    "fairness_cost_rules": "公平性与代价规则"
  }}
---