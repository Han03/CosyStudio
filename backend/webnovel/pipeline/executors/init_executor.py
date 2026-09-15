"""执行器：深度初始化执行器。

参考webnovel-writer的webnovel-init SKILL，实现深度初始化流程。
使用LLM生成详细设定：金手指、角色、反派、力量体系、世界观、总纲等。
"""

import json
import os
import re
from typing import Dict, Any
from ..base_executor import BaseExecutor, ExecutorResult
from core.model_executor import get_model_executor
from utils.logger import log_manager
from utils.llm_json_parser import parse_llm_json

_logger = log_manager.get_logger("init_executor")


def _parse_chapter_num(value, default: int = 1) -> int:
    """从可能含非数字字符（如'20章'）的值中解析章节编号。"""
    if isinstance(value, int):
        return value
    if not value:
        return default
    match = re.search(r'\d+', str(value))
    return int(match.group()) if match else default


def _safe_items(value):
    """安全地将值转换为 dict 列表，跳过非 dict 元素。

    LLM 可能返回字符串列表而非 dict 列表，此函数过滤掉非 dict 元素。
    """
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _safe_str(value) -> str:
    """安全地将值转换为字符串，处理 dict/list 类型。"""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return ""


# ── 题材模板部分 → 中文标签映射（文本渲染用，未覆盖的 key 用原名兜底）──
_GENRE_PART_FIELD_LABELS = {
    "worldview": {
        "description": "世界描述", "dynasty_features": "朝代特点",
        "dynasty": "朝代", "features": "特点", "core_conflict": "核心冲突",
        "social_class": "社会阶层", "class": "阶层", "upward_path": "上升路径",
        "power_system": "权力机构", "institution": "机构", "function": "职能", "power": "权力",
    },
    "power_system": {
        "description": "体系描述", "promotion_paths": "晋升路径",
        "imperial_examination": "科举", "military_merit": "军功", "family_connection": "荫补",
        "political_resources": "政治资源", "resource": "资源", "acquisition": "获取",
        "court_game": "朝堂博弈", "information_war": "情报战", "personnel_war": "人事战",
        "policy_war": "政策战",
    },
    "golden_finger_guidelines": {
        "types": "类型", "fit_requirements": "契合要求",
    },
    "character_guidelines": {
        "protagonist_archetypes": "主角原型", "villain_types": "反派类型",
        "supporting_roles": "配角定位", "role": "角色", "relationship": "关系",
        "relationship_patterns": "关系模式",
    },
}

# 条目（list[dict] 元素）内部字段的标签覆盖：处理与顶层同 key 不同语义的字段
_GENRE_PART_ENTRY_LABELS = {
    "power_system": {"description": "说明"},
    "character_guidelines": {"function": "职能"},
}

# 跨题材通用字段 → 中文标签（各题材 JSON 结构差异大，part 映射未覆盖的常见字段在此兜底）
_GENRE_COMMON_FIELD_LABELS = {
    "name": "名称", "type": "类型", "types": "类型", "level": "等级", "levels": "等级体系",
    "features": "特点", "feature": "特点", "rules": "规则", "rule": "规则",
    "cost": "代价", "costs": "代价", "role": "定位", "faction": "势力", "factions": "势力",
    "conflict": "冲突", "relation": "关系", "relations": "关系", "example": "示例",
    "knowledge": "知识", "ability": "能力", "abilities": "能力", "description": "描述",
    "function": "职能", "resources": "资源", "resource": "资源", "risk": "风险",
    "stage": "阶段", "stages": "阶段", "ending": "结局", "template": "模板", "templates": "模板",
    "status": "地位", "identity": "身份", "goal": "目标", "purpose": "目的",
    "method": "方式", "methods": "方式", "requirement": "要求", "requirements": "要求",
    "limitation": "限制", "limits": "限制", "trait": "特质", "traits": "特质",
    "element": "要素", "elements": "要素", "content": "内容", "category": "类别",
    "core": "核心", "style": "风格", "mood": "基调", "tone": "基调",
    "title": "称号", "rank": "品级", "grade": "品级", "position": "职位",
    "structure": "结构", "design": "设计", "system": "体系", "mechanism": "机制",
    "source": "来源", "origin": "起源", "influence": "影响", "effect": "效果",
    "value": "数值", "boundary": "边界", "condition": "条件", "trigger": "触发",
    "principle": "原则", "principles": "原则", "pattern": "模式", "patterns": "模式",
    "growth": "成长", "path": "路径", "paths": "路径", "arc": "弧线",
    "hook": "钩子", "clue": "线索", "clues": "线索", "twist": "反转", "payoff": "爽点",
    "setup": "铺垫", "climax": "高潮", "ending_types": "结局类型", "pacing": "节奏",
    # 题材特有高频字段（单段 key）
    "lifespan": "寿命", "nature": "本质", "people": "人群", "gongdou": "宫斗",
    "quanmou": "权谋", "zhaidou": "宅斗", "affection": "情感羁绊", "cooldown": "冷却",
    "threat": "威胁", "analysis": "分析", "collection": "收集", "emotion": "情感",
    "bond": "羁绊", "race": "种族", "races": "种族", "danger": "危险",
    "obvious": "显性", "hidden": "隐性", "misleading": "误导", "percentage": "占比",
    "reveal": "揭示", "layer": "层级", "opportunities": "机遇", "economy": "经济",
    "politics": "政治", "marriage": "婚姻", "angle": "角度", "issue": "议题",
    "note": "说明", "handling": "处理", "scene": "场景", "plot": "剧情",
    "dilemma": "困境", "school": "学派", "energy": "能量", "field": "领域",
    "means": "手段", "games": "博弈", "explicit": "显性", "interaction": "互动",
    "attitude": "态度", "drive": "驱动力", "realm": "境界", "usage": "运用",
    "acquisition": "获取", "domain": "领域", "agriculture": "农业", "commerce": "商贸",
    "industry": "产业", "military": "军事", "era": "时代", "eras": "时代",
    "atmosphere": "氛围", "categories": "类别", "power": "实力", "recovery": "恢复",
    "impact": "影响", "advancement": "晋升", "promotion": "晋升", "workplace": "职场",
    "roles": "角色", "identities": "身份", "scenes": "场景", "character": "角色",
    "boss": "霸总", "president": "总裁", "sweet": "甜宠", "pain": "虐点",
    "abuse": "虐", "chase": "追", "rising": "高潮", "hooks": "钩子",
    "templates": "模板", "items": "物件", "situations": "处境", "periods": "时期",
    "forms": "形态", "pillars": "支柱", "commandments": "诫律", "suspect": "嫌疑人",
    "trick": "骗术", "triangle": "三角", "transformation": "转变", "stages": "阶段",
    "response": "应对", "transmission": "传递", "counter": "反制", "intelligence": "情报",
    "daily": "日常", "prevention": "防范", "emergency": "紧急", "methods": "方式",
    "factors": "因素", "success": "成功", "live": "直播", "key": "关键",
    "team": "团队", "teams": "队伍", "positions": "岗位", "dimension": "维度",
    "rhythm": "节奏", "game": "游戏", "matches": "比赛", "victory": "胜利",
    "league": "联赛", "early": "前期", "mid": "中期", "late": "后期",
    "growth": "成长", "content": "内容", "function": "职能", "institution": "机构",
    "building": "建设", "talent": "天赋", "core": "核心", "task": "任务",
    "internal": "内部", "affairs": "事务", "domestic": "家庭", "life": "生活",
    "management": "管理", "view": "观", "world": "世界", "conflict": "冲突",
    "types": "类型", "alien": "外星", "social": "社会", "clauses": "条款",
    "contracts": "契约", "duration": "期限", "reason": "原因", "rank": "品级",
    "ranks": "品级", "status": "地位", "harem": "后宫", "secret": "秘术",
    "open": "明面", "taboo": "禁忌", "red": "红线", "lines": "线", "defense": "防御",
    "development": "发展", "ending": "结局", "features": "特点", "opponent": "对手",
    "relation": "关系", "eighties": "八十年代", "nineties": "九十年代",
    "sixties": "六十年代", "seventies": "七十年代", "elements": "要素",
    "systems": "体系", "worldview": "世界观", "domestic": "家庭", "life": "生活",
    "story": "故事", "opening": "开篇", "templates": "模板", "structure": "结构",
    "emotion": "情感", "relation": "关系", "plot": "剧情", "scenes": "场景",
    "conflicts": "冲突", "mechanics": "机制", "background": "背景", "options": "选项",
    "family": "家族", "resource": "资源", "resources": "资源", "title": "称号",
    "number": "数量", "identity": "身份", "contract": "契约", "clause": "条款",
    "asset": "资产", "scale": "规模", "power": "权力", "nature": "本质",
    "features": "特点", "core": "核心", "rules": "规则", "system": "体系",
    "levels": "等级体系", "level": "等级", "name": "名称", "type": "类型",
    "rule": "规则", "cost": "代价", "role": "定位", "faction": "势力",
    "factions": "势力", "conflict": "冲突", "relation": "关系", "example": "示例",
    "knowledge": "知识", "ability": "能力", "description": "描述", "function": "职能",
    "risk": "风险", "stage": "阶段", "template": "模板", "method": "方式",
    "requirement": "要求", "limitation": "限制", "trait": "特质", "element": "要素",
    "content": "内容", "category": "类别", "style": "风格", "tone": "基调",
    "title": "称号", "grade": "品级", "position": "职位", "structure": "结构",
    "design": "设计", "mechanism": "机制", "source": "来源", "origin": "起源",
    "influence": "影响", "effect": "效果", "value": "数值", "boundary": "边界",
    "condition": "条件", "trigger": "触发", "principle": "原则", "pattern": "模式",
    "growth": "成长", "path": "路径", "arc": "弧线", "principles": "原则",
    "patterns": "模式", "paths": "路径", "purpose": "目的", "limits": "限制",
    "methods": "方式", "goals": "目标", "stages": "阶段", "types": "类型",
    # 题材特有高频单段词（单段 key 只走本表，不经过分词表）
    "lifespan": "寿命", "nature": "本质", "people": "人群", "gongdou": "宫斗",
    "quanmou": "权谋", "zhaidou": "宅斗", "affection": "情感羁绊", "cooldown": "冷却",
    "threat": "威胁", "analysis": "分析", "collection": "收集", "emotion": "情感",
    "bond": "羁绊", "race": "种族", "races": "种族", "danger": "危险",
    "obvious": "显性", "hidden": "隐性", "misleading": "误导", "percentage": "占比",
    "reveal": "揭示", "layer": "层级", "opportunities": "机遇", "economy": "经济",
    "politics": "政治", "marriage": "婚姻", "angle": "角度", "issue": "议题",
    "note": "说明", "handling": "处理", "scene": "场景", "plot": "剧情",
    "dilemma": "困境", "school": "学派", "energy": "能量", "field": "领域",
    "means": "手段", "games": "博弈", "explicit": "显性", "interaction": "互动",
    "attitude": "态度", "drive": "驱动力", "realm": "境界", "usage": "运用",
    "acquisition": "获取", "domain": "领域", "agriculture": "农业", "commerce": "商贸",
    "industry": "产业", "military": "军事", "era": "时代", "eras": "时代",
    "atmosphere": "氛围", "categories": "类别", "power": "实力", "recovery": "恢复",
    "impact": "影响", "advancement": "晋升", "promotion": "晋升", "workplace": "职场",
    "roles": "角色", "identities": "身份", "scenes": "场景", "character": "角色",
    "boss": "霸总", "president": "总裁", "sweet": "甜宠", "pain": "虐点",
    "abuse": "虐", "chase": "追", "rising": "高潮", "hooks": "钩子",
    "templates": "模板", "items": "物件", "situations": "处境", "periods": "时期",
    "forms": "形态", "pillars": "支柱", "commandments": "诫律", "suspect": "嫌疑人",
    "trick": "骗术", "triangle": "三角", "transformation": "转变", "stages": "阶段",
    "response": "应对", "transmission": "传递", "counter": "反制", "intelligence": "情报",
    "daily": "日常", "prevention": "防范", "emergency": "紧急", "methods": "方式",
    "factors": "因素", "success": "成功", "live": "直播", "key": "关键",
    "team": "团队", "teams": "队伍", "positions": "岗位", "dimension": "维度",
    "rhythm": "节奏", "game": "游戏", "matches": "比赛", "victory": "胜利",
    "league": "联赛", "early": "前期", "mid": "中期", "late": "后期",
    "growth": "成长", "content": "内容", "function": "职能", "institution": "机构",
    "building": "建设", "talent": "天赋", "core": "核心", "task": "任务",
    "internal": "内部", "affairs": "事务", "domestic": "家庭", "life": "生活",
    "management": "管理", "view": "观", "world": "世界", "conflict": "冲突",
    "types": "类型", "alien": "外星", "social": "社会", "clauses": "条款",
    "contracts": "契约", "duration": "期限", "reason": "原因", "rank": "品级",
    "ranks": "品级", "status": "地位", "harem": "后宫", "secret": "秘术",
    "open": "明面", "taboo": "禁忌", "red": "红线", "lines": "线", "defense": "防御",
    "development": "发展", "ending": "结局", "features": "特点", "opponent": "对手",
    "relation": "关系", "eighties": "八十年代", "nineties": "九十年代",
    "sixties": "六十年代", "seventies": "七十年代", "elements": "要素",
    "systems": "体系", "worldview": "世界观", "story": "故事", "opening": "开篇",
    "structure": "结构", "conflicts": "冲突", "mechanics": "机制", "background": "背景",
    "options": "选项", "family": "家族", "resource": "资源", "resources": "资源",
    "title": "称号", "number": "数量", "identity": "身份", "contract": "契约",
    "clause": "条款", "asset": "资产", "scale": "规模", "principles": "原则",
    "patterns": "模式", "paths": "路径", "purpose": "目的", "limits": "限制",
    "goals": "目标", "information": "信息", "manifestation": "显现", "suspense": "悬念",
    "treatment": "处理", "society": "社会", "work": "工作", "agency": "机构",
    "female": "女性", "male": "男性", "middle": "中期", "rarity": "稀有度",
    "period": "时期", "bp": "扳选", "training": "训练", "importance": "重要性",
    "income": "收入", "responsibility": "职责", "formula": "套路", "formulas": "套路",
    "steps": "步骤", "dimensions": "维度", "expression": "表达", "solution": "方案",
    "during": "直播中", "pre": "直播前", "strategy": "策略", "inheritance": "继承",
    "probability": "概率", "quality": "资质", "changeable": "可变", "difficult": "困难",
    "unchangeable": "不可变", "time": "时代", "white": "白", "moon": "月光",
    "stand": "替", "in": "身", "ten": "十", "post": "直播后", "tournament": "锦标赛",
    "tournaments": "锦标赛",
}

# 复合 key 分词词段 → 中文（用于 female_archetypes → 女性原型 等组合字段）
_GENRE_WORD_SEGMENT_LABELS = {
    "female": "女性", "male": "男性", "protagonist": "主角", "antagonist": "反派",
    "villain": "反派", "supporting": "配角", "archetype": "原型", "archetypes": "原型",
    "opponent": "对手", "ally": "盟友", "team": "团队", "role": "角色",
    "relationship": "关系", "relation": "关系", "pattern": "模式", "patterns": "模式",
    "type": "类型", "types": "类型", "category": "类别", "categories": "类别",
    "ability": "能力", "abilities": "能力", "skill": "技能", "power": "实力",
    "level": "等级", "levels": "等级", "realm": "境界", "grade": "品级", "rank": "品级",
    "rule": "规则", "rules": "规则", "design": "设计", "principle": "原则", "principles": "原则",
    "detail": "细节", "details": "细节", "depth": "深度", "authenticity": "真实性",
    "scene": "场景", "character": "角色", "gray": "灰色", "dimension": "维度", "dimensions": "维度",
    "emotion": "情感", "fate": "命运", "magic": "魔法", "school": "学派", "schools": "学派",
    "social": "社会", "conflict": "冲突", "conflicts": "冲突", "source": "来源", "sources": "来源",
    "attitude": "态度", "interaction": "互动", "development": "发展", "growth": "成长",
    "ending": "结局", "opportunity": "机遇", "opportunities": "机遇", "success": "成功",
    "factor": "因素", "factors": "因素", "economy": "经济", "marriage": "婚姻", "era": "时代",
    "eras": "时代", "feature": "特点", "features": "特点", "element": "要素", "elements": "要素",
    "technique": "技巧", "structure": "结构", "mechanism": "机制", "mechanisms": "机制",
    "example": "示例", "cost": "代价", "costs": "代价", "threat": "威胁", "twist": "反转",
    "clue": "线索", "clues": "线索", "layer": "层级", "layers": "层级", "question": "问题",
    "layering": "分层", "reveal": "揭示", "requirement": "要求", "requirements": "要求",
    "sanity": "理智", "truth": "真相", "nature": "本质", "information": "情报",
    "acquisition": "获取", "physiology": "生理", "lifespan": "寿命", "combat": "战斗",
    "martial": "武学", "arts": "技艺", "upgrade": "升级", "awakening": "觉醒",
    "evolution": "进化", "material": "材料", "materials": "材料", "rarity": "稀有度",
    "position": "岗位", "post": "岗位", "rhythm": "节奏", "victory": "胜利", "match": "比赛",
    "league": "联赛", "traffic": "流量", "agriculture": "农业", "industry": "产业",
    "commerce": "商贸", "military": "军事", "talent": "天赋", "institution": "机构",
    "building": "建设", "domain": "领域", "tech": "科技", "cyber": "赛博", "body": "身体",
    "field": "领域", "mechanic": "机制", "mechanics": "机制", "method": "方式",
    "strategy": "策略", "cooldown": "冷却", "probability": "概率", "inheritance": "继承",
    "affection": "情感", "background": "背景", "offspring": "后代", "quality": "资质",
    "system": "体系", "panel": "面板", "panels": "面板", "core": "核心", "key": "关键",
    "danger": "危险", "spirit": "灵异", "spirits": "灵异", "faction": "势力",
    "factions": "势力", "level": "等级", "levels": "等级", "era": "时代",
    "humanity": "人性", "spectrum": "光谱", "resource": "资源", "resources": "资源",
    "recovery": "恢复", "limitation": "限制", "limitations": "限制", "usage": "运用",
    "history": "历史", "intervention": "干预", "knowledge": "知识", "people": "人群",
    "goal": "目标", "impact": "影响", "risk": "风险", "cost": "代价",
    "obvious": "显性", "hidden": "隐性", "misleading": "误导", "percentage": "占比",
    "motive": "动机", "reasoning": "推理", "elements": "要素", "identity": "身份",
    "relationship": "关系", "role": "角色", "rules": "规则", "type": "类型",
    "template": "模板", "core": "核心", "survival": "生存", "rate": "率",
    "player": "玩家", "ecosystem": "生态", "difficulty": "难度", "resource": "资源",
    "era": "时代", "feature": "特点", "features": "特点", "battle": "战斗",
    "decision": "决策", "breakthrough": "突破", "win": "胜利", "lose": "败北",
    "tactic": "战术", "loop": "循环", "feedback": "反馈", "node": "节点", "nodes": "节点",
    "plot": "剧情", "scene": "场景", "setting": "设定", "settings": "设定",
    "culture": "文化", "custom": "风俗", "customs": "风俗", "religion": "信仰",
    "belief": "信仰", "ideology": "意识形态", "class": "阶层", "classes": "阶层",
    "status": "地位", "rank": "品级", "family": "家族", "clan": "宗门", "clans": "宗门",
    "sect": "宗门", "sects": "宗门", "realm": "境界", "realms": "境界", "tier": "层级",
    "tiers": "层级", "level": "等级", "wave": "波次", "round": "回合", "turn": "回合",
    "war": "战争", "battle": "战役", "campaign": "战役", "strategy": "战略",
    "tactic": "战术", "scheme": "计谋", "schemes": "计谋", "intrigue": "权谋",
    "conspiracy": "阴谋", "betrayal": "背叛", "ally": "盟友", "enemy": "敌人",
    "king": "君主", "emperor": "皇帝", "court": "朝堂", "official": "官员",
    "officials": "官员", "bureaucracy": "官僚", "govern": "治理", "governance": "治理",
    "admin": "内政", "administration": "内政", "affairs": "事务", "affair": "事务",
    "domestic": "家庭", "life": "生活", "world": "世界", "view": "观",
    "management": "管理", "tasks": "任务", "task": "任务", "internal": "内部",
    "external": "外部", "public": "公开", "secret": "隐秘", "open": "明面",
    "taboo": "禁忌", "red": "红线", "line": "线", "lines": "线", "defense": "防御",
    "offense": "进攻", "attack": "攻击", "counter": "反制", "resist": "抵抗",
    "weakness": "弱点", "strength": "优势", "advantage": "优势", "disadvantage": "劣势",
    "reward": "奖励", "punishment": "惩罚", "penalty": "惩罚", "bonus": "加成",
    "attribute": "属性", "attributes": "属性", "stat": "数值", "stats": "数值",
    "effect": "效果", "effects": "效果", "buff": "增益", "debuff": "减益",
    "heal": "治疗", "damage": "伤害", "defense": "防御", "armor": "护甲",
    "speed": "速度", "agility": "敏捷", "intelligence": "智力", "wisdom": "智慧",
    "strength": "力量", "constitution": "体质", "luck": "幸运", "charm": "魅力",
    "weight": "权重", "ratio": "比例", "rate": "比率", "count": "数量",
    "number": "数量", "amount": "数量", "total": "总计", "max": "上限", "min": "下限",
    "average": "平均", "sum": "总和", "first": "第一", "last": "最后",
    "early": "前期", "mid": "中期", "late": "后期", "begin": "开始", "end": "结束",
    "open": "开局", "middle": "中段", "final": "结局", "stage": "阶段", "stages": "阶段",
    "progress": "进度", "process": "流程", "flow": "流程", "chain": "链路",
    "route": "路线", "routes": "路线", "branch": "分支", "tree": "树", "trees": "树",
    "module": "模块", "component": "组件", "part": "部分", "section": "部分",
    "chapter": "章节", "chapters": "章节", "volume": "卷", "volumes": "卷",
    "word": "字", "words": "字", "count": "数", "ratio": "比", "three": "三",
    "second": "秒", "contrast": "对比", "chase": "追", "wife": "妻", "face": "打脸",
    "slap": "打脸", "slapping": "打脸", "rebirth": "重生", "revenge": "复仇",
    "story": "故事", "rising": "高潮", "face": "打脸", "setup": "铺垫",
    # 补充段（复合 key 常用组成部分）
    "with": "与", "past": "过去", "present": "当下", "cause": "成因", "effect": "影响",
    "human": "人类", "framework": "框架", "frameworks": "框架", "ranks": "品级",
    "relationships": "关系", "dilemmas": "困境", "mystery": "悬疑", "potential": "潜在",
    "suspense": "悬念", "manifestation": "显现", "eighties": "八十年代", "nineties": "九十年代",
    "sixties": "六十年代", "seventies": "七十年代", "middle": "中期", "options": "选项",
    "settings": "设定", "rarity": "稀有度", "items": "物件", "situations": "处境",
    "historical": "历史", "periods": "时期", "period": "时期", "training": "训练",
    "esports": "电竞", "ecology": "生态", "formula": "套路", "formulas": "套路",
    "points": "要点", "career": "职业", "dimensions": "维度", "issues": "议题",
    "meaning": "含义", "emotional": "情感", "positions": "岗位", "during": "直播中",
    "pre": "直播前", "post": "直播后", "rhythm": "节奏", "roles": "角色",
    "templates": "模板", "openings": "开篇", "hooks": "钩子", "management": "管理",
    "pillars": "支柱", "work": "工作", "agency": "机构", "agencies": "机构",
    "society": "社会", "triangle": "三角", "transformation": "转变", "stages": "阶段",
    "plot": "剧情", "scene": "场景", "function": "职能", "boss": "霸总",
    "president": "总裁", "sweet": "甜宠", "pain": "虐点", "triggers": "触发",
    "asset": "资产", "scale": "规模", "anomaly": "异常", "hierarchy": "层级",
    "identities": "身份", "complexity": "复杂性", "origin": "起源", "trait": "特质",
    "evolution": "进化", "promotion": "晋升", "workplace": "职场", "paths": "路径",
    "family": "家族", "domestic": "家庭", "life": "生活", "worldview": "世界观",
    "power": "实力", "management": "管理", "alien": "外星", "forms": "形态",
    "suspect": "嫌疑人", "trick": "骗术", "core": "核心", "contract": "契约",
    "clauses": "条款", "duration": "期限", "reason": "原因", "status": "地位",
    "harem": "后宫", "secret": "秘术", "open": "明面", "taboo": "禁忌",
    "red": "红线", "lines": "线", "defense": "防御", "methods": "方式",
    "development": "发展", "ending": "结局", "features": "特点", "opponent": "对手",
    "relation": "关系", "elements": "要素", "success": "成功", "factors": "因素",
    "opportunities": "机遇", "economy": "经济", "politics": "政治", "marriage": "婚姻",
    "era": "时代", "eras": "时代", "angle": "角度", "issue": "议题", "note": "说明",
    "handling": "处理", "dilemma": "困境", "school": "学派", "energy": "能量",
    "field": "领域", "means": "手段", "games": "博弈", "explicit": "显性",
    "interaction": "互动", "attitude": "态度", "drive": "驱动力", "realm": "境界",
    "usage": "运用", "acquisition": "获取", "domain": "领域", "agriculture": "农业",
    "commerce": "商贸", "industry": "产业", "military": "军事", "atmosphere": "氛围",
    "categories": "类别", "recovery": "恢复", "impact": "影响", "advancement": "晋升",
    "characters": "角色", "scenes": "场景", "lifespan": "寿命", "nature": "本质",
    "people": "人群", "affection": "情感羁绊", "cooldown": "冷却", "threat": "威胁",
    "analysis": "分析", "collection": "收集", "emotion": "情感", "bond": "羁绊",
    "race": "种族", "danger": "危险", "obvious": "显性", "hidden": "隐性",
    "misleading": "误导", "percentage": "占比", "reveal": "揭示", "layer": "层级",
    "intelligence": "情报", "daily": "日常", "prevention": "防范", "emergency": "紧急",
    "response": "应对", "transmission": "传递", "counter": "反制", "key": "关键",
    "team": "团队", "teams": "队伍", "dimension": "维度", "game": "游戏",
    "matches": "比赛", "victory": "胜利", "league": "联赛", "early": "前期",
    "mid": "中期", "late": "后期", "growth": "成长", "content": "内容",
    "institution": "机构", "building": "建设", "talent": "天赋", "task": "任务",
    "internal": "内部", "affairs": "事务", "view": "观", "world": "世界",
    "conflicts": "冲突", "mechanics": "机制", "background": "背景",
    "information": "信息", "manifestation": "显现", "suspense": "悬念", "treatment": "处理",
    "society": "社会", "work": "工作", "agency": "机构", "female": "女性", "male": "男性",
    "middle": "中期", "rarity": "稀有度", "period": "时期", "bp": "扳选",
    "training": "训练", "importance": "重要性", "income": "收入", "responsibility": "职责",
    "formula": "套路", "formulas": "套路", "steps": "步骤", "dimensions": "维度",
    "expression": "表达", "solution": "方案", "during": "直播中", "pre": "直播前",
    "strategy": "策略", "inheritance": "继承", "probability": "概率", "quality": "资质",
    "changeable": "可变", "difficult": "困难", "unchangeable": "不可变",
    "time": "时代", "white": "白", "moon": "月光", "stand": "替", "in": "身",
    "ten": "十", "importance": "重要性", "income": "收入", "responsibility": "职责",
}


def _genre_compound_label(key: str) -> str:
    """复合 key 分词翻译：female_archetypes → 女性原型；无法全段命中则返回原名。

    词段先查分词表，再回落通用字段表（两表常用词有重叠，回落避免漏翻）。
    """
    segments = str(key).split("_")
    if len(segments) < 2:
        return str(key)
    parts = []
    for seg in segments:
        zh = _GENRE_WORD_SEGMENT_LABELS.get(seg) or _GENRE_COMMON_FIELD_LABELS.get(seg)
        if not zh:
            return str(key)  # 任一段未命中即放弃（避免拼出错误语义）
        parts.append(zh)
    return "".join(parts)


def _genre_field_label(part_name: str, key: str) -> str:
    """取题材部分的字段中文标签：part 映射 → 通用映射 → 复合分词 → 原 key 兜底。"""
    labels = _GENRE_PART_FIELD_LABELS.get(part_name) or {}
    if key in labels:
        return labels[key]
    if key in _GENRE_COMMON_FIELD_LABELS:
        return _GENRE_COMMON_FIELD_LABELS[key]
    compound = _genre_compound_label(key)
    return compound if compound != str(key) else str(key)


def _genre_entry_label(part_name: str, key: str) -> str:
    """取 list[dict] 条目内部字段的标签（先查条目级覆盖，再回落字段映射）。"""
    entries = _GENRE_PART_ENTRY_LABELS.get(part_name) or {}
    if key in entries:
        return entries[key]
    return _genre_field_label(part_name, key)


def _genre_scalar_text(value) -> str:
    """标量值 → 文本。"""
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def _genre_list_text(part_name: str, items, prefix: str = "") -> str:
    """list 渲染：全标量 → 顿号一行；含 dict → 每元素一行 '- 条目'。"""
    if not items:
        return ""
    if all(not isinstance(it, (dict, list)) for it in items):
        vals = [_genre_scalar_text(it) for it in items if it not in (None, "")]
        return f"{prefix}{'、'.join(vals)}" if vals else ""
    lines = []
    for it in items:
        if isinstance(it, dict):
            parts = []
            for k, v in it.items():
                if v in (None, ""):
                    continue
                if isinstance(v, (dict, list)):
                    continue  # 嵌套结构由子小节承接，条目内只放标量
                parts.append(f"{_genre_entry_label(part_name, k)}：{_genre_scalar_text(v)}")
            if parts:
                lines.append(f"{prefix}- {' ｜ '.join(parts)}")
        elif isinstance(it, list):
            sub = _genre_list_text(part_name, it, prefix=f"{prefix}  ")
            if sub:
                lines.append(sub)
        else:
            if it not in (None, ""):
                lines.append(f"{prefix}- {_genre_scalar_text(it)}")
    return "\n".join(lines)


def _genre_dict_text(part_name: str, d: dict, prefix: str = "") -> str:
    """dict 渲染：标量值 → '标签：值'；list 值 → 子小节+条目；嵌套 dict → 递归。"""
    lines = []
    for k, v in d.items():
        if v in (None, ""):
            continue
        label = _genre_field_label(part_name, k)
        if isinstance(v, dict):
            sub = _genre_dict_text(part_name, v, prefix=f"{prefix}  ")
            if sub:
                lines.append(f"{prefix}{label}：")
                lines.append(sub)
        elif isinstance(v, list):
            if not v:
                continue
            if all(not isinstance(it, (dict, list)) for it in v):
                vals = [_genre_scalar_text(it) for it in v if it not in (None, "")]
                if vals:
                    lines.append(f"{prefix}{label}：{'、'.join(vals)}")
            else:
                sub = _genre_list_text(part_name, v, prefix=f"{prefix}  ")
                if sub:
                    lines.append(f"{prefix}{label}：")
                    lines.append(sub)
        else:
            lines.append(f"{prefix}{label}：{_genre_scalar_text(v)}")
    return "\n".join(lines)


def format_genre_part_text(part_name: str, part_data) -> str:
    """将题材模板指定部分（dict/list/str）渲染为易读文本。

    替代 json.dumps 直接注入：字段带中文标签、列表分条、去除 JSON 符号噪声。
    空结构返回 ""（沿用"空区块不渲染"语义）。
    """
    if part_data is None:
        return ""
    if isinstance(part_data, str):
        return part_data if part_data.strip() else ""
    if isinstance(part_data, list):
        return _genre_list_text(part_name, part_data)
    if isinstance(part_data, dict):
        return _genre_dict_text(part_name, part_data)
    return str(part_data) if part_data else ""


def _sanitize_value(value, default=""):
    """将LLM返回的值转换为SQLite支持的类型（str/int/float/None）。"""
    if value is None:
        return default
    if isinstance(value, (str, int, float)):
        return value
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (list, dict)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


class DictObj:
    """将 dict 递归转换为属性访问对象，供 prompt format_map 使用。"""
    def __init__(self, d):
        for k, v in d.items():
            if isinstance(v, dict):
                setattr(self, k, DictObj(v))
            else:
                setattr(self, k, v)

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(f"'DictObj' object has no attribute '{name}'")
        return DictObj({}) if name in ['protagonist', 'golden_finger', 'power_system', 'worldview', 'world'] else ""


from webnovel.repositories import (
    add_webnovel_project, get_webnovel_project_by_script, update_webnovel_project,
    delete_webnovel_project,
    add_golden_finger, add_golden_finger_upgrade, add_golden_finger_payoff, add_golden_finger_feedback,
    add_power_system, add_power_level, add_power_feedback,
    add_worldview, add_worldview_faction, add_worldview_history, update_worldview,
    add_volume_outline, add_volume_crisis,
    add_genre_fusion,
    add_webnovel_state, add_plot_thread,
    add_chapter_meta,
    add_idea_bank, update_idea_bank,
    get_idea_bank_by_project,
    get_character_cards_by_project,
)
from repositories import update_script

from .story_system_executor import StorySystemExecutor
from .character_builder_executor import CharacterBuilderExecutor


class InitExecutor(BaseExecutor):
    """深度初始化执行器。"""

    step_name = "init_executor"
    step_description = "深度初始化项目"
    step_weight = 15

    def __init__(self, script_id: int, chapter_index: int, task_id: int, progress_callback=None, interrupt_check=None):
        super().__init__(script_id, chapter_index, task_id)
        self._progress_callback = progress_callback
        self._interrupt_check = interrupt_check

    async def _notify_progress(self, step: str, message: str, progress: int):
        """通知进度并持久化到 scripts 表，以便页面刷新后恢复进度条"""
        # 持久化进度到数据库，页面刷新后可恢复
        try:
            update_script(self.script_id, progress=progress, progress_message=message)
        except Exception as e:
            _logger.warning(f"[init_executor] 持久化进度失败: {e}")
        # WebSocket 实时通知
        if self._progress_callback:
            try:
                await self._progress_callback(step, message, progress)
            except Exception as e:
                _logger.warning(f"[init_executor] 进度通知失败: {e}")

    def _check_interrupted(self):
        """检查是否被中断"""
        if self._interrupt_check and self._interrupt_check():
            raise InterruptedError("初始化被用户中断")

    @staticmethod
    def _sanitize_value(value, default=""):
        """将LLM返回的值转换为SQLite支持的类型（委托到模块级函数）。"""
        return _sanitize_value(value, default)

    @staticmethod
    def _normalize_step5_worldview(raw: Dict) -> tuple:
        """将第 5 步用户/AI 填写的世界观数据映射到 webnovel_worldview 表字段。

        返回 (mapped_wv_dict, factions_list, history_list)。
        """
        mapped = {}
        field_map = {
            "geography": "core_regions",
            "key_locations": "important_locations",
            "social_class": "social_hierarchy",
            "currency_system": "currency_system",
            "sect_hierarchy": "political_rules",
            "cultivation_chain": "cultivation_chain",
        }
        for src, dst in field_map.items():
            val = raw.get(src, "")
            if isinstance(val, str) and val.strip():
                mapped[dst] = val.strip()

        # scale → continent_count（尝试解析数字）
        scale = raw.get("scale", "")
        if isinstance(scale, str) and scale.strip():
            scale_map = {"单城": 1, "多城": 3, "大陆": 5, "多界": 8}
            mapped["continent_count"] = scale_map.get(scale.strip(), 3)

        # 直接匹配的同名字段
        for key in ("world_summary", "main_genre", "sub_genre", "fusion_mechanism",
                     "core_regions", "edge_regions", "social_hierarchy",
                     "resource_distribution", "belief_ideology", "resource_scarcity",
                     "political_rules", "social_common_sense", "hard_constraints",
                     "energy_cycle", "technology_basis", "fairness_cost_rules"):
            if key in raw and raw[key]:
                mapped[key] = raw[key]

        # ── 解析 factions（换行分隔字符串 → dict 列表，行内支持顿号/逗号分隔多势力）──
        factions = []
        factions_raw = raw.get("factions", "")
        if isinstance(factions_raw, str) and factions_raw.strip():
            for line in factions_raw.strip().split("\n"):
                line = line.strip().strip("-").strip("·").strip("•").strip()
                if not line:
                    continue
                # 一行内可能用顿号/逗号分隔多个势力（如"正道宗门、魔道宗派"）
                for name in re.split(r"[、，,;；]", line):
                    name = name.strip()
                    if name:
                        factions.append({"faction_name": name, "tier": "", "relation": "", "hierarchy": ""})
        elif isinstance(factions_raw, list):
            factions = [f for f in factions_raw if isinstance(f, dict)]

        # ── 解析 history（换行分隔字符串 → dict 列表）──
        history_events = []
        history_raw = raw.get("history", "") or raw.get("history_events", "")
        if isinstance(history_raw, str) and history_raw.strip():
            for line in history_raw.strip().split("\n"):
                line = line.strip().strip("-").strip("·").strip("•").strip()
                if line:
                    # 尝试拆分 "时代: 事件" 格式
                    if "：" in line:
                        era, event = line.split("：", 1)
                    elif ": " in line:
                        era, event = line.split(": ", 1)
                    else:
                        era, event = "", line
                    history_events.append({"era": era.strip(), "event": event.strip()})
        elif isinstance(history_raw, list):
            history_events = [e for e in history_raw if isinstance(e, dict)]

        return mapped, factions, history_events

    def _load_genre_json_template(self, genre: str) -> Dict[str, Any]:
        """加载题材JSON模板。"""
        if not genre:
            return {}
        
        genre_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "prompts", "genres_json", f"{genre}.json"
        )
        if not os.path.exists(genre_path):
            _logger.info(f"[init_executor] 题材JSON模板不存在: {genre}")
            return {}
        
        with open(genre_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        try:
            template_data = json.loads(content)
            _logger.info(f"[init_executor] 加载题材JSON模板成功: {genre}，包含: {list(template_data.keys())}")
            return template_data
        except json.JSONDecodeError as e:
            _logger.error(f"[init_executor] 题材模板JSON解析失败: {e}")
            return {}

    def _get_genre_template_part(self, genre_template: Dict[str, Any], part_name: str) -> str:
        """获取题材模板的指定部分内容。"""
        if not genre_template:
            return ""
        
        part_data = genre_template.get(part_name)
        if part_data is None:
            return ""
        if isinstance(part_data, dict):
            if not part_data:
                return ""  # 空 dict 不渲染为 "{}"
            return json.dumps(part_data, ensure_ascii=False)
        elif isinstance(part_data, list):
            if not part_data:
                return ""  # 空 list 不渲染为 "[]"
            return json.dumps(part_data, ensure_ascii=False)
        else:
            return str(part_data) if part_data else ""

    def _get_genre_template_part_text(
        self, genre_template: Dict[str, Any], part_name: str,
    ) -> str:
        """获取题材模板指定部分，渲染为易读文本（替代 JSON 注入）。

        用于世界观/力量体系/金手指参考/角色指南等知识性区块：
        字段带中文标签、列表分条、去除 JSON 符号噪声，提升 LLM 参考效率。
        """
        if not genre_template:
            return ""
        return format_genre_part_text(part_name, genre_template.get(part_name))

    def _load_csv_knowledge_text(self, table_name: str, genre: str, header: str = "") -> str:
        """从 CSV 知识表按题材加载知识并格式化为直接注入文本。
        
        若精确题材无匹配，回退查询 applicable_genre='全局' 的行作为兜底。
        """
        try:
            from webnovel.repositories.csv_knowledge_repository import (
                query_csv_knowledge, format_csv_knowledge_for_prompt
            )
            genre_column = "genre" if table_name == "webnovel_csv_verdict_rules" else "applicable_genre"
            rows = query_csv_knowledge(table_name, genre=genre, genre_column=genre_column)
            # 若精确题材无匹配，回退查询"全局"数据
            if not rows and genre_column != "genre":
                rows = query_csv_knowledge(table_name, genre="全局", genre_column=genre_column)
            return format_csv_knowledge_for_prompt(table_name, rows, header=header)
        except Exception as e:
            _logger.warning(f"[init_executor] 加载CSV知识失败({table_name}): {e}")
            return ""

    def _load_anti_trope_rules(self, genre: str) -> str:
        """加载反套路规则。"""
        rules_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "prompts", "anti_trope_rules.json"
        )
        if not os.path.exists(rules_path):
            _logger.info(f"[init_executor] 反套路规则文件不存在")
            return ""
        
        with open(rules_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        try:
            rules_data = json.loads(content)
            genre_rules = rules_data.get("anti_trope_rules", {}).get(genre, [])
            general_rules = rules_data.get("anti_trope_rules", {}).get("通用", [])
            
            all_rules = genre_rules + general_rules
            _logger.info(f"[init_executor] 加载反套路规则成功: {genre}，共{len(all_rules)}条")
            
            if all_rules:
                return "\n".join([f"- {rule}" for rule in all_rules])
            return ""
        except json.JSONDecodeError as e:
            _logger.error(f"[init_executor] 反套路规则JSON解析失败: {e}")
            return ""

    async def _call_llm(self, prompt_name: str, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """调用LLM生成数据。"""
        executor = get_model_executor()
        prompt_data = self._load_prompt(prompt_name)
        
        if not prompt_data["user_prompt"]:
            _logger.error(f"[init_executor] {prompt_name} 的user_prompt为空")
            return {}
        
        try:
            # ============== 安全 format：缺失字段自动填充空值，不再抛 KeyError ==============
            class _SafeAttr:
                """访问不存在的属性时返回空字符串，适配 {obj.missing_attr} 格式的占位符。"""
                def __getattr__(self, _name: str):
                    return ""
                def __getitem__(self, _idx):
                    return ""
                def __str__(self):
                    return ""
                def __repr__(self):
                    return ""
                def __bool__(self):
                    return False
                def __iter__(self):
                    return iter([])
                def __len__(self):
                    return 0

            class _SafeFormatMap(dict):
                """format_map 专用 dict：缺失 key 时自动返回 _SafeAttr()，避免 KeyError。"""
                def __missing__(self, key: str):
                    _logger.warning(
                        f"[init_executor] prompt={prompt_name} 引用了缺失的上下文字段: {{{key}}}，已用空值填充"
                    )
                    return _SafeAttr()

            user_prompt = prompt_data["user_prompt"].format_map(_SafeFormatMap(**context_data))

            project_id = 0
            try:
                from webnovel.repositories import get_webnovel_project_by_script
                _proj = get_webnovel_project_by_script(self.script_id)
                if _proj:
                    project_id = _proj.get("id", 0)
            except Exception:
                pass

            import time as _time
            _call_start = _time.time()

            result = await executor.execute_text_chat(
                prompt=user_prompt,
                system_prompt=prompt_data["system_prompt"],
                max_tokens=4000,
                script_id=self.script_id,
                project_id=project_id,
                executor_name="init_executor",
                prompt_name=prompt_name,
            )
            _latency_ms = int((_time.time() - _call_start) * 1000)

            content = result.get("content", "") if result else ""
            content = content.strip()

            json_result = parse_llm_json(
                content,
                script_id=self.script_id,
                project_id=project_id,
                executor_name="init_executor",
                prompt_name=prompt_name,
                model_name=result.get("model_name", "") if isinstance(result, dict) else "",
                system_prompt=prompt_data["system_prompt"],
                user_prompt=user_prompt,
                input_tokens=result.get("input_tokens", 0) if isinstance(result, dict) else 0,
                output_tokens=result.get("output_tokens", 0) if isinstance(result, dict) else 0,
                latency_ms=_latency_ms,
            )

            if json_result:
                _logger.info(f"[init_executor] JSON解析成功，键: {list(json_result.keys())}")
                return json_result
            else:
                _logger.error(f"[init_executor] JSON解析失败，所有策略均失败")
                return {"raw_content": content}
        except Exception as e:
            _logger.error(f"[init_executor] LLM调用异常: {e}")
            return {"error": str(e)}

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行深度初始化。"""
        project_id = None  # 提前声明，异常回滚时可访问
        try:
            script_id = self.script_id
            project_data = context.get("project_data", {})

            await self._notify_progress("start", "开始深度初始化", 5)

            basic_fields = {
                "script_id": script_id,
                "title": project_data.get("title", ""),
                "genre": project_data.get("genre", ""),
                "genre_label": project_data.get("genre_label", ""),
                "target_words": project_data.get("target_words", 0),
                "target_chapters": project_data.get("target_chapters", 0),
                "one_liner": project_data.get("one_liner", ""),
                "story_summary": project_data.get("story_summary", ""),
                "core_conflict": project_data.get("core_conflict", ""),
                "target_reader": project_data.get("target_reader", ""),
                "platform": project_data.get("platform", ""),
                "anti_trope_rules": project_data.get("anti_trope_rules", ""),
                "hard_constraints": project_data.get("hard_constraints", ""),
                "core_selling_points": project_data.get("core_selling_points", ""),
                "opening_hook": project_data.get("opening_hook", ""),
                "protagonist_name": project_data.get("protagonist_name", ""),
                "protagonist_flaw": project_data.get("protagonist_flaw", ""),
                "villain_mirror": project_data.get("villain_mirror", ""),
                "protagonist_desire": project_data.get("protagonist_desire", ""),
                "protagonist_archetype": project_data.get("protagonist_archetype", ""),
                "protagonist_structure": project_data.get("protagonist_structure", "单主角"),
                "heroine_config": project_data.get("heroine_config", ""),
                "heroine_names": project_data.get("heroine_names", ""),
                "heroine_role": project_data.get("heroine_role", ""),
                "co_protagonists": project_data.get("co_protagonists", ""),
                "co_protagonist_roles": project_data.get("co_protagonist_roles", ""),
                "antagonist_tiers": project_data.get("antagonist_tiers", ""),
                "antagonist_level": project_data.get("antagonist_level", ""),
                "golden_finger_name": project_data.get("golden_finger_name", ""),
                "golden_finger_type": project_data.get("golden_finger_type", ""),
                "golden_finger_style": project_data.get("golden_finger_style", ""),
                "gf_visibility": project_data.get("gf_visibility", ""),
                "gf_irreversible_cost": project_data.get("gf_irreversible_cost", ""),
                "world_scale": project_data.get("world_scale", ""),
                "factions": project_data.get("factions", ""),
                "power_system_type": project_data.get("power_system_type", ""),
                "social_class": project_data.get("social_class", ""),
                "resource_distribution": project_data.get("resource_distribution", ""),
                "currency_system": project_data.get("currency_system", ""),
                "currency_exchange": project_data.get("currency_exchange", ""),
                "sect_hierarchy": project_data.get("sect_hierarchy", ""),
                "cultivation_chain": project_data.get("cultivation_chain", ""),
                "cultivation_subtiers": project_data.get("cultivation_subtiers", "")
            }

            project = add_webnovel_project(**basic_fields)
            project_id = project["id"]

            # 为空值用户输入字段生成 _desc 后缀版本，避免 prompt 中冒号后为空白
            for _field in ("story_summary", "antagonist_tiers"):
                project[f"{_field}_desc"] = project.get(_field, "") or "（未填写）"

            self._check_interrupted()
            await self._notify_progress("project", "项目基础信息已创建", 10)

            genre_json_template = self._load_genre_json_template(project_data.get("genre", ""))

            llm_context = {
                "project": DictObj(project),
                "protagonist": DictObj({}),
                "golden_finger": DictObj({}),
                "power_system": DictObj({}),
                "worldview": DictObj({}),
                "world": DictObj({}),
                "genre_core_selling_points": self._get_genre_template_part(genre_json_template, "core_selling_points"),
                "genre_worldview": self._get_genre_template_part_text(genre_json_template, "worldview"),
                "genre_power_system": self._get_genre_template_part_text(genre_json_template, "power_system"),
                "genre_outline_structure": self._get_genre_template_part(genre_json_template, "outline_structure"),
                "genre_character_guidelines": self._get_genre_template_part_text(genre_json_template, "character_guidelines"),
                "genre_golden_finger_guidelines": self._get_genre_template_part_text(genre_json_template, "golden_finger_guidelines"),
                "genre_story_rules": self._get_genre_template_part(genre_json_template, "story_rules"),
                "genre_subgenres": self._get_genre_template_part(genre_json_template, "subgenres"),
                "genre_creative_constraints": self._get_genre_template_part(genre_json_template, "creative_constraints"),
                "_project_id": project_id,
            }

            # ============== 预填充领域对象：将前端用户输入注入 llm_context，供后续所有 LLM 调用参考 ==============
            # 主角基础信息（角色卡尚未构建，但前端已提供基础数据）
            llm_context["protagonist"] = DictObj({
                "name": project_data.get("protagonist_name", ""),
                "personality_flaw": project_data.get("protagonist_flaw", ""),
                "flaw": project_data.get("protagonist_flaw", ""),
                "desire": project_data.get("protagonist_desire", ""),
                "true_desire": project_data.get("protagonist_desire", ""),
                "archetype": project_data.get("protagonist_archetype", ""),
                "structure": project_data.get("protagonist_structure", "单主角"),
            })

            # 金手指用户数据（LLM 生成前注入，让 LLM 参考用户选择）
            llm_context["golden_finger"] = DictObj({
                "type": project_data.get("golden_finger_type", ""),
                "name": project_data.get("golden_finger_name", ""),
                "style": project_data.get("golden_finger_style", ""),
                "visibility": project_data.get("gf_visibility", ""),
                "irreversible_cost": project_data.get("gf_irreversible_cost", ""),
            })

            # 世界观用户数据（修复 constraints/master_outline 中 {world.scale} 等为空的问题）
            llm_context["world"] = DictObj({
                "scale": project_data.get("world_scale", ""),
                "power_system_type": project_data.get("power_system_type", ""),
                "factions": project_data.get("factions", ""),
                "social_class": project_data.get("social_class", ""),
                "resource_distribution": project_data.get("resource_distribution", ""),
                "currency_system": project_data.get("currency_system", ""),
                "sect_hierarchy": project_data.get("sect_hierarchy", ""),
                "cultivation_chain": project_data.get("cultivation_chain", ""),
            })

            # ============== 加载 CSV 知识（按题材 × 步骤精准注入）=============
            # 先设置默认空值，确保 prompt 模板占位符不会 KeyError
            llm_context["golden_finger_knowledge"] = ""
            llm_context["genre_tone_knowledge"] = ""
            llm_context["naming_knowledge"] = ""

            _genre = project_data.get("genre", "")
            if _genre:
                # 金手指设计知识 → init_power_system 步骤使用
                _gf_knowledge = self._load_csv_knowledge_text("webnovel_csv_golden_finger", _genre)
                if _gf_knowledge:
                    llm_context["golden_finger_knowledge"] = _gf_knowledge

                # 题材基调知识 → init_worldview 步骤使用
                _tone_knowledge = self._load_csv_knowledge_text("webnovel_csv_genre_tone", _genre)
                if _tone_knowledge:
                    llm_context["genre_tone_knowledge"] = _tone_knowledge

                # 命名规则知识 → init_worldview_factions 步骤使用
                _naming_knowledge = self._load_csv_knowledge_text("webnovel_csv_naming", _genre)
                if _naming_knowledge:
                    llm_context["naming_knowledge"] = _naming_knowledge

            worldview_data = project_data.get("worldview")
            user_has_worldview = bool(worldview_data and isinstance(worldview_data, dict) and any(
                str(v).strip() for v in worldview_data.values() if isinstance(v, str)
            ))

            if user_has_worldview:
                # ── 用户已填写第 5 步：以用户数据为主，LLM 仅补充缺失字段 ──
                mapped_wv, user_factions, user_history = self._normalize_step5_worldview(worldview_data)

                # 检查关键字段是否缺失，若缺失则调用 LLM 补充
                key_fields = ["world_summary", "core_regions", "social_hierarchy", "social_common_sense"]
                missing_keys = [k for k in key_fields if not mapped_wv.get(k)]

                if missing_keys:
                    self._check_interrupted()
                    _logger.info(f"[init_executor] 用户世界观缺失字段: {missing_keys}，调用 LLM 补充")
                    # 将已有映射数据注入上下文，让 LLM 基于用户输入补充
                    llm_context["worldview"] = DictObj(mapped_wv)
                    supplement = await self._call_llm("init_worldview", llm_context)
                    if supplement and "error" not in supplement:
                        supplement.pop("factions", None)
                        supplement.pop("history_events", None)
                        for key in list(supplement.keys()):
                            val = self._sanitize_value(supplement[key], "")
                            if val and not mapped_wv.get(key):
                                mapped_wv[key] = val

                wv_data = mapped_wv
                factions = user_factions
                history_events = user_history
            else:
                # ── 用户未填写：完全由 LLM 生成 ──
                self._check_interrupted()
                worldview_data = await self._call_llm("init_worldview", llm_context)

                if worldview_data and "error" not in worldview_data:
                    wv_data = worldview_data.copy()
                    wv_data.pop("factions", None)
                    wv_data.pop("history_events", None)
                    factions = []
                    history_events = []
                else:
                    wv_data = {}
                    factions = []
                    history_events = []

            if wv_data:
                # 统一安全转换
                for key in list(wv_data.keys()):
                    wv_data[key] = self._sanitize_value(wv_data[key], "")

                wv = add_worldview(project_id, **wv_data)
                wv_id = wv["id"]

                # 将用户已有的势力/历史数据注入上下文，供 LLM 补充时参考
                existing_factions_text = ""
                if factions:
                    existing_factions_text = "\n".join([
                        f"- {f.get('faction_name', '')}"
                        + (f"（{f.get('tier', '')}）" if f.get('tier') else "")
                        for f in _safe_items(factions) if f.get("faction_name")
                    ])
                existing_history_text = ""
                if history_events:
                    existing_history_text = "\n".join([
                        f"- {e.get('era', '')}: {e.get('event', '')}" if e.get('era') else f"- {e.get('event', '')}"
                        for e in _safe_items(history_events) if e.get("event")
                    ])
                llm_context["existing_factions_text"] = existing_factions_text or "（用户未提供势力数据，请全新设计）"
                llm_context["existing_history_text"] = existing_history_text or "（用户未提供历史数据，请全新设计）"

                # 关键：在势力/历史步骤前回写补全后的完整世界观，保证 init_worldview_factions
                # 的【已有世界观】区块与 plan_master_outline 的【世界观核心设定】同源（完整数据）
                llm_context["worldview"] = DictObj(wv_data)

                # 势力/历史：用户数据优先，缺失部分由 LLM 补充
                if not factions and not history_events:
                    # 用户未提供势力和历史，完全由 LLM 生成
                    self._check_interrupted()
                    faction_history_data = await self._call_llm("init_worldview_factions", llm_context)
                    if faction_history_data and "error" not in faction_history_data:
                        factions = faction_history_data.get("factions", [])
                        history_events = faction_history_data.get("history_events", [])
                        if isinstance(factions, str):
                            factions = []
                        if isinstance(history_events, str):
                            history_events = []
                elif not factions or not history_events:
                    # 用户提供了部分，LLM 补充缺失的另一半
                    self._check_interrupted()
                    faction_history_data = await self._call_llm("init_worldview_factions", llm_context)
                    if faction_history_data and "error" not in faction_history_data:
                        # factions：若 LLM 返回完善结果则以 LLM 为准（prompt 已约束"在此基础上
                        # 补充完善"，返回即为完整列表），避免用户原始合并文本/缺字段数据直接入库
                        _llm_factions = faction_history_data.get("factions", [])
                        if isinstance(_llm_factions, str):
                            _llm_factions = []
                        if _llm_factions:
                            factions = _llm_factions
                        if not history_events:
                            history_events = faction_history_data.get("history_events", [])
                            if isinstance(history_events, str):
                                history_events = []

                for faction in _safe_items(factions):
                    faction_data = {
                        "faction_name": self._sanitize_value(faction.get("faction_name", "")),
                        "tier": self._sanitize_value(faction.get("tier", "")),
                        "relation": self._sanitize_value(faction.get("relation", "")),
                        "hierarchy": self._sanitize_value(faction.get("hierarchy", ""))
                    }
                    add_worldview_faction(wv_id, **faction_data)

                for event in _safe_items(history_events):
                    add_worldview_history(
                        wv_id,
                        self._sanitize_value(event.get("era", "")),
                        self._sanitize_value(event.get("event", ""))
                    )

                # 将势力/历史摘要聚合写入主表，确保不依赖子表查询的下游也能获得核心信息
                factions_summary = "、".join([
                    self._sanitize_value(f.get("faction_name", ""))
                    for f in _safe_items(factions) if self._sanitize_value(f.get("faction_name", ""))
                ])
                if factions_summary:
                    current_hierarchy = wv_data.get("social_hierarchy", "")
                    new_hierarchy = f"{current_hierarchy}\n势力格局：{factions_summary}" if current_hierarchy else f"势力格局：{factions_summary}"
                    update_worldview(wv_id, social_hierarchy=new_hierarchy)

                history_summary = "；".join([
                    f"{self._sanitize_value(e.get('era', ''))}: {self._sanitize_value(e.get('event', ''))}"
                    for e in _safe_items(history_events)[:5]
                    if self._sanitize_value(e.get('event', ''))
                ])
                if history_summary:
                    current_summary = wv_data.get("world_summary", "")
                    new_summary = f"{current_summary}\n历史脉络：{history_summary}" if current_summary else f"历史脉络：{history_summary}"
                    update_worldview(wv_id, world_summary=new_summary)
                
                llm_context["worldview"] = DictObj(wv_data)

            self._check_interrupted()
            await self._notify_progress("worldview", "世界观设定已完成", 20)

            # ============== 金手指详细设定：基于用户选择的方向调用专用 prompt 生成完整设定（含升级路线/爽点/反馈节奏子表），用户基本字段覆盖 ==============
            gf_user_flat = {
                "type": project_data.get("golden_finger_type", ""),
                "name": project_data.get("golden_finger_name", ""),
                "style": project_data.get("golden_finger_style", ""),
                "visibility": project_data.get("gf_visibility", ""),
                "irreversible_cost": project_data.get("gf_irreversible_cost", ""),
                "growth_rhythm": project_data.get("gf_growth_rhythm", "")
            }
            user_has_basic_gf = bool(gf_user_flat["type"] or gf_user_flat["name"])

            _logger.info(f"[init_executor] 调用 LLM 生成金手指详细设定（用户基本字段: {'有' if user_has_basic_gf else '无'}）")
            golden_finger_data = await self._call_llm("init_golden_finger_detail", llm_context)

            if not golden_finger_data or "error" in golden_finger_data:
                error_msg = golden_finger_data.get("error", "LLM返回空内容") if golden_finger_data else "LLM返回空内容"
                _logger.error(f"[init_executor] 金手指 LLM 调用失败: {error_msg}")
                return ExecutorResult(success=False, error_message=f"金手指设定生成失败: {error_msg}")

            gf_data = golden_finger_data.copy()
            upgrade_path = gf_data.pop("upgrade_path", [])
            payoff_points = gf_data.pop("payoff_points", gf_data.pop("payoff", []))
            feedback_nodes = gf_data.pop("feedback_nodes", gf_data.pop("_nodes", []))

            # 用户已填写的基本字段覆盖 LLM 生成的值
            if user_has_basic_gf:
                for key, val in gf_user_flat.items():
                    if val:
                        gf_data[key] = val

            gf_data["irreversible_cost"] = gf_data.pop("irre_cost", gf_data.get("irreversible_cost", ""))

            # 字段映射：name→main_role（金手指名称存主要作用列）；
            # style 仅在 LLM 未生成 visual_expression 时兜底；growth_rhythm→cost_limitation
            if "name" in gf_data:
                gf_data["main_role"] = gf_data.pop("name")
                gf_data["name"] = gf_data["main_role"]  # 保留副本，供 prompt {golden_finger.name} 引用
            if "style" in gf_data:
                style_val = gf_data.pop("style")
                if not gf_data.get("visual_expression"):
                    gf_data["visual_expression"] = style_val
            if "growth_rhythm" in gf_data:
                gf_data["cost_limitation"] = gf_data.pop("growth_rhythm")

            # 安全转换所有字段类型
            for key in list(gf_data.keys()):
                gf_data[key] = self._sanitize_value(gf_data[key], "")

            _logger.info(f"[init_executor] 准备保存金手指，gf_data keys: {list(gf_data.keys())}")
            _logger.info(f"[init_executor] gf_data sample: {str(gf_data)[:200]}")

            gf = add_golden_finger(project_id, **gf_data)
            gf_id = gf["id"]

            for upgrade in _safe_items(upgrade_path):
                add_golden_finger_upgrade(gf_id, upgrade.get("stage", ""), upgrade.get("description", ""))

            for payoff in _safe_items(payoff_points):
                add_golden_finger_payoff(gf_id, payoff.get("type", ""), payoff.get("description", ""))

            for feedback in _safe_items(feedback_nodes):
                add_golden_finger_feedback(gf_id, feedback.get("type", ""), feedback.get("chapter_interval", 0), feedback.get("description", ""))

            if not (_safe_items(upgrade_path) or _safe_items(payoff_points) or _safe_items(feedback_nodes)):
                _logger.warning(
                    f"[init_executor] 金手指子表数据为空（升级路线/爽点/反馈节奏均未生成），"
                    f"LLM返回键: {list(golden_finger_data.keys()) if golden_finger_data else 'None'}"
                )

            llm_context["golden_finger"] = DictObj(gf_data)

            self._check_interrupted()
            await self._notify_progress("golden_finger", "金手指设定已完成", 30)

            # ============== 角色构建（委托给 CharacterBuilderExecutor）=============
            char_builder = CharacterBuilderExecutor(self.script_id, 0, 0)

            protagonist_data, protagonist_id = await char_builder.build_protagonist(project_data, llm_context)

            self._check_interrupted()
            await self._notify_progress("protagonist", "主角设定已完成", 40)

            heroine_data_list, heroine_id_list = await char_builder.build_heroine(project_data, llm_context)

            self._check_interrupted()
            await self._notify_progress("heroine", "女主设定已完成", 45)

            villain_data, villain_id = await char_builder.build_villain(project_data, llm_context)

            self._check_interrupted()
            await self._notify_progress("villain", "反派设定已完成", 50)

            power_system_data = project_data.get("power_system")
            if not power_system_data:
                self._check_interrupted()
                power_system_data = await self._call_llm("init_power_system", llm_context)
            
            if power_system_data and "error" not in power_system_data:
                ps_data = power_system_data.copy()
                power_levels = ps_data.pop("power_levels", [])
                power_feedbacks = ps_data.pop("power_feedbacks", [])
                
                # 统一安全转换：和 villain/golden_finger/character_card 保持一致
                for key in list(ps_data.keys()):
                    ps_data[key] = self._sanitize_value(ps_data[key], "")
                
                ps = add_power_system(project_id, **ps_data)
                ps_id = ps["id"]

                for level in _safe_items(power_levels):
                    level_data = {
                        "level_order": self._sanitize_value(level.get("level_order", 0), 0),
                        "level_name": self._sanitize_value(level.get("level_name", "")),
                        "core_abilities": self._sanitize_value(level.get("core_abilities", "")),
                        "resource_requirements": self._sanitize_value(level.get("resource_requirements", "")),
                        "breakthrough_method": self._sanitize_value(level.get("breakthrough_method", "")),
                        "failure_cost": self._sanitize_value(level.get("failure_cost", "")),
                        "overlevel_cost": self._sanitize_value(level.get("overlevel_cost", ""))
                    }
                    add_power_level(ps_id, **level_data)

                for feedback in _safe_items(power_feedbacks):
                    feedback_data = {
                        "realm_change_chapter": self._sanitize_value(
                            feedback.get("realm_change_chapter", feedback.get("chapter", 0)), 0),
                        "power_gap_display": self._sanitize_value(
                            feedback.get("power_gap_display", feedback.get("description", "")))
                    }
                    add_power_feedback(ps_id, **feedback_data)
                
                llm_context["power_system"] = DictObj(ps_data)

            self._check_interrupted()
            await self._notify_progress("power_system", "力量体系已完成", 60)

            llm_context["anti_trope_rules"] = self._load_anti_trope_rules(project_data.get("genre", ""))

            constraints_data = project_data.get("constraints")
            if not constraints_data:
                constraints_data = await self._call_llm("init_constraints", llm_context)
            
            if constraints_data and "error" not in constraints_data:
                constraint_packages = _safe_items(constraints_data.get("constraint_packages", []))
                if constraint_packages:
                    best_package = max(constraint_packages, key=lambda x:
                        sum(x.get("scoring", {}).values()) / len(x.get("scoring", {}))
                        if isinstance(x.get("scoring"), dict) and x.get("scoring") else 0
                    )
                    
                    update_webnovel_project(
                        project_id,
                        anti_trope_rules=best_package.get("anti_trope_rule", ""),
                        hard_constraints=json.dumps(best_package.get("hard_constraints", []), ensure_ascii=False),
                        core_selling_points=best_package.get("one_liner_selling_point", ""),
                        opening_hook=best_package.get("opening_hook", ""),
                        protagonist_flaw=best_package.get("protagonist_flaw_driven", ""),
                        villain_mirror=best_package.get("antagonist_mirror", ""),
                    )

            # 约束包+叠加包：按题材从 CSV 加载，注入总纲生成 prompt
            if _genre:
                try:
                    from webnovel.repositories import (
                        get_csv_packs_by_genre, format_pack_for_prompt, filter_packs_by_template)
                    _packs = get_csv_packs_by_genre(_genre)
                    # 策略 a：通用叠加包只保留题材模板点名的 1 个，题材类包保持运行时匹配
                    _packs = filter_packs_by_template(
                        _packs, llm_context.get("genre_creative_constraints", ""))
                    _packs_text = format_pack_for_prompt(_packs)
                    if _packs_text:
                        llm_context["csv_constraint_packs"] = _packs_text
                except Exception as e:
                    _logger.warning(f"[init_executor] 加载约束包失败: {e}")

            master_outline_data = project_data.get("master_outline")
            if not master_outline_data:
                self._check_interrupted()
                master_outline_data = await self._call_llm("plan_master_outline", llm_context)
            
            if master_outline_data and "error" not in master_outline_data:
                volumes = master_outline_data.get("volumes", [])
                plot_threads = master_outline_data.get("plot_threads", [])
                
                for volume in _safe_items(volumes):
                    chapter_range = volume.get("chapter_range", "1-10")
                    if isinstance(chapter_range, int):
                        chapter_start = chapter_range
                        chapter_end = chapter_range + 9
                    else:
                        chapter_range_str = str(chapter_range)
                        if '-' in chapter_range_str:
                            parts = chapter_range_str.split("-")
                            chapter_start = _parse_chapter_num(parts[0]) if parts[0].strip() else 1
                            chapter_end = _parse_chapter_num(parts[1], 10) if len(parts) > 1 and parts[1].strip() else 10
                        else:
                            chapter_start = _parse_chapter_num(chapter_range_str) if chapter_range_str.strip() else 1
                            chapter_end = chapter_start + 9

                    vo_data = {
                        "volume_name": volume.get("volume_name", ""),
                        "chapter_start": chapter_start,
                        "chapter_end": chapter_end,
                        "core_conflict": volume.get("core_conflict", ""),
                        "volume_climax": volume.get("volume_climax", ""),
                        "promise_description": volume.get("protagonist_growth", ""),
                    }
                    # volume_number 必须作为单独位置参数传入（函数签名是 add_volume_outline(project_id, volume_number, **kwargs)），
                    # 不能放在 **vo_data 中，否则会报 "got multiple values for argument 'volume_number'"
                    vo_num = _parse_chapter_num(volume.get("volume_number", 0), 0)
                    vo = add_volume_outline(project_id, vo_num, **vo_data)

                for thread in _safe_items(plot_threads):
                    # 将LLM返回的丰富字段映射到DB的精简结构(thread_type/content/status/chapter)
                    content_parts = []
                    if thread.get("thread_name"):
                        content_parts.append(f"线程名: {thread['thread_name']}")
                    key_events = thread.get("key_events", [])
                    if key_events:
                        events_str = ", ".join(key_events) if isinstance(key_events, list) else str(key_events)
                        content_parts.append(f"关键事件: {events_str}")
                    end_ch = _parse_chapter_num(thread.get("end_chapter", 100), 100)
                    content_parts.append(f"结束章节: {end_ch}")
                    if thread.get("resolution"):
                        content_parts.append(f"解决方式: {thread['resolution']}")
                    add_plot_thread(
                        project_id,
                        thread_type=thread.get("thread_type", "主线"),
                        content=" | ".join(content_parts),
                        status=thread.get("resolution", ""),
                        chapter=_parse_chapter_num(thread.get("start_chapter", 1), 1),
                    )

            elif project_data.get("volume_outlines"):
                for vo_data in _safe_items(project_data["volume_outlines"]):
                    crises = vo_data.pop("crises", [])
                    if not isinstance(crises, list):
                        crises = []
                    # volume_number 必须作为位置参数单独传入（见函数签名和L779-L782注释）
                    vo_num = _parse_chapter_num(vo_data.pop("volume_number", 0), 0)
                    vo = add_volume_outline(project_id, vo_num, **vo_data)
                    vo_id = vo["id"]
                    for i, crisis in enumerate(crises):
                        crisis_text = _safe_str(crisis) if not isinstance(crisis, str) else crisis
                        add_volume_crisis(vo_id, crisis_order=i + 1, crisis_event=crisis_text)

            self._check_interrupted()
            await self._notify_progress("master_outline", "总纲与卷纲已完成", 75)

            gf_data_raw = project_data.get("genre_fusion")
            if isinstance(gf_data_raw, dict):
                gf_data = gf_data_raw.copy()
                for key in list(gf_data.keys()):
                    gf_data[key] = self._sanitize_value(gf_data[key], "")
                add_genre_fusion(project_id, **gf_data)

            # 构建已有角色名单，注入 llm_context 供 init_character_group prompt 引用
            all_cards = get_character_cards_by_project(project_id)
            _type_label = {
                "protagonist": "主角", "co_protagonist": "主角团核心", "heroine": "女主",
                "villain": "反派", "supporting": "配角", "minor": "龙套",
            }
            _char_lines = []
            for card in all_cards:
                cname = card.get("name", "")
                if not cname:
                    continue
                ctype = _type_label.get(card.get("character_type", ""), card.get("character_type", ""))
                identity = card.get("identity", "")
                desc = f"{cname}({ctype})"
                if identity:
                    desc += f" - {identity}"
                _char_lines.append(desc)
            llm_context["existing_characters_section"] = "\n".join(_char_lines) if _char_lines else "（暂无已有角色）"
            character_group_data, character_group_id = await char_builder.build_character_group(project_data, llm_context)

            self._check_interrupted()
            await self._notify_progress("character_group", "角色组已完成", 85)

            add_webnovel_state(project_id, current_chapter=0, total_words=0, current_volume=1)

            if project_data.get("plot_threads"):
                for thread in _safe_items(project_data["plot_threads"]):
                    add_plot_thread(
                        project_id,
                        thread_type=self._sanitize_value(thread.get("thread_type", "")),
                        content=self._sanitize_value(thread.get("content", "")),
                        status=self._sanitize_value(thread.get("status", "")),
                        chapter=self._sanitize_value(thread.get("chapter", 0), 0)
                    )

            selected_idea = {
                "title": project_data.get("title", ""),
                "one_liner": project_data.get("one_liner", ""),
                "anti_trope": project_data.get("anti_trope_rules", ""),
                "hard_constraints": project_data.get("hard_constraints", []) if isinstance(project_data.get("hard_constraints"), list) else []
            }
            
            constraints_inherited = {
                "anti_trope": project_data.get("anti_trope_rules", ""),
                "hard_constraints": project_data.get("hard_constraints", []),
                "protagonist_flaw": project_data.get("protagonist_flaw", ""),
                "antagonist_mirror": project_data.get("villain_mirror", ""),
                "opening_hook": project_data.get("opening_hook", "")
            }
            
            add_idea_bank(project_id, selected_idea, constraints_inherited)

            _logger.info(f"[init_executor] 生成Story System合同")
            story_system = StorySystemExecutor(script_id, 0, 0)
            story_system_result = await story_system.execute({})
            if story_system_result.success:
                _logger.info(f"[init_executor] Story System合同生成成功")
            else:
                _logger.warning(f"[init_executor] Story System合同生成失败: {story_system_result.error_message}")

            self._check_interrupted()
            await self._notify_progress("story_system", "Story System合同已完成", 92)

            await self._notify_progress("completed", "深度初始化完成", 100)

            summary = f"深度初始化完成：项目ID={project_id}"
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={"project_id": project_id, "project": project}
            )

        except InterruptedError as e:
            # 回滚：若 project 记录已创建则清理，避免下次重试时被判定为"已初始化"
            if project_id is not None:
                try:
                    delete_webnovel_project(project_id)
                    _logger.info(f"[init_executor] 初始化中断，已清理 project_id={project_id}")
                except Exception as clean_ex:
                    _logger.warning(f"[init_executor] 清理失败 project_id={project_id}: {clean_ex}")
            await self._notify_progress("interrupted", "初始化已中断", 0)
            return ExecutorResult(
                success=False,
                error_message=f"初始化被中断: {str(e)}",
                step_summary="深度初始化被用户中断"
            )
        except Exception as e:
            # 回滚：若 project 记录已创建则清理，避免下次重试时被判定为"已初始化"
            if project_id is not None:
                try:
                    delete_webnovel_project(project_id)
                    _logger.info(f"[init_executor] 初始化失败，已回滚清理 project_id={project_id}")
                except Exception as clean_ex:
                    _logger.warning(f"[init_executor] 回滚清理失败 project_id={project_id}: {clean_ex}")
            await self._notify_progress("failed", f"初始化失败: {str(e)}", 0)
            return ExecutorResult(
                success=False,
                error_message=f"深度初始化执行失败: {str(e)}",
                step_summary="深度初始化执行失败"
            )