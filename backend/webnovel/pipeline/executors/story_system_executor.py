"""执行器：Story System 合同生成器。

参考webnovel-writer的story-system命令，生成MASTER_SETTING和anti_patterns。
"""

import json
from typing import Dict, Any, List
from ..base_executor import BaseExecutor, ExecutorResult
from webnovel.repositories import (
    get_webnovel_project_by_script, get_worldview_by_project,
    get_power_system_by_project, get_golden_finger_by_project,
    get_character_cards_by_project, get_villain_by_project,
    get_idea_bank_by_project,
    save_master_setting, save_anti_patterns
)


class StorySystemExecutor(BaseExecutor):
    """Story System 合同生成器。"""

    step_name = "story_system"
    step_description = "生成Story System合同"
    step_weight = 10

    async def execute(self, context: Dict[str, Any]) -> ExecutorResult:
        """执行Story System合同生成。"""
        try:
            script_id = self.script_id

            project = get_webnovel_project_by_script(script_id)
            if not project:
                return ExecutorResult(
                    success=False,
                    error_message="项目不存在",
                    step_summary="项目不存在"
                )
            project_id = project["id"]

            genre = project.get("genre", "玄幻")
            title = project.get("title", "")

            worldview = get_worldview_by_project(project_id)
            power_system = get_power_system_by_project(project_id)
            golden_finger = get_golden_finger_by_project(project_id)
            protagonists = get_character_cards_by_project(project_id, "protagonist")
            villain = get_villain_by_project(project_id)
            idea_bank = get_idea_bank_by_project(project_id)

            master_setting = self._generate_master_setting(
                project, worldview, power_system, golden_finger,
                protagonists, villain, idea_bank
            )

            anti_patterns_data = self._generate_anti_patterns(project, idea_bank)

            save_master_setting(project_id, master_setting)
            save_anti_patterns(project_id, anti_patterns_data.get("anti_patterns", []))

            summary = f"Story System合同生成完成：MASTER_SETTING、anti_patterns已存入数据库"
            return ExecutorResult(
                success=True,
                step_summary=summary,
                output_data={
                    "project_id": project_id,
                    "genre": genre
                }
            )

        except Exception as e:
            return ExecutorResult(
                success=False,
                error_message=f"Story System合同生成失败: {str(e)}",
                step_summary="Story System合同生成失败"
            )

    def _generate_master_setting(
        self, project: Dict, worldview: Dict, power_system: Dict,
        golden_finger: Dict, protagonists: list, villain: Dict, idea_bank: Dict
    ) -> Dict:
        """生成MASTER_SETTING.json内容。"""
        protagonist = protagonists[0] if protagonists else {}

        core_constraints = []
        if idea_bank:
            constraints = idea_bank.get("constraints_inherited", {})
            if constraints.get("anti_trope"):
                core_constraints.append({"type": "anti_trope", "value": constraints["anti_trope"]})
            hard_constraints = constraints.get("hard_constraints", [])
            # 修复 bug: hard_constraints 可能是 JSON 字符串（从数据库读取时），需要先解析
            if isinstance(hard_constraints, str):
                try:
                    parsed = json.loads(hard_constraints)
                    if isinstance(parsed, list):
                        hard_constraints = parsed
                    else:
                        # 不是列表，按换行拆分
                        hard_constraints = [s.strip() for s in parsed.split("\n") if s.strip()]
                except (json.JSONDecodeError, TypeError):
                    # 普通字符串，按换行拆分
                    hard_constraints = [s.strip() for s in hard_constraints.split("\n") if s.strip()]
            if isinstance(hard_constraints, list):
                for hc in hard_constraints:
                    if isinstance(hc, str) and hc.strip():
                        core_constraints.append({"type": "hard_constraint", "value": hc.strip()})

        return {
            "project": {
                "title": project.get("title", ""),
                "genre": project.get("genre", ""),
                "target_words": project.get("target_words", 0),
                "target_chapters": project.get("target_chapters", 0),
                "one_liner": project.get("one_liner", ""),
                "core_conflict": project.get("core_conflict", ""),
                "target_reader": project.get("target_reader", ""),
                "platform": project.get("platform", "")
            },
            "protagonist": {
                "name": protagonist.get("name", ""),
                "desire": protagonist.get("desire", "") or protagonist.get("short_term_goal", ""),
                "flaw": protagonist.get("flaw", "") or protagonist.get("personality_flaw", ""),
                "archetype": protagonist.get("archetype", ""),
                "growth_arc": protagonist.get("growth_arc", {})
            },
            "golden_finger": {
                "type": golden_finger.get("type", ""),
                "name": golden_finger.get("main_role", "") or golden_finger.get("name", ""),
                "irreversible_cost": golden_finger.get("irreversible_cost", ""),
                "limitations": golden_finger.get("cost_limitation", ""),
                "visibility": golden_finger.get("visibility", "")
            },
            "world": {
                "scale": worldview.get("scale", "") or worldview.get("world_scale", ""),
                "power_system_type": power_system.get("system_type", "") if power_system else "",
                "social_hierarchy": worldview.get("social_hierarchy", ""),
                "factions": self._parse_json_field(worldview.get("factions", ""))
            },
            "power_system": {
                "core_creed": power_system.get("core_creed", "") if power_system else "",
                "cost_rules": power_system.get("cost_rules", "") if power_system else "",
                "fairness_principle": power_system.get("fairness_principle", "") if power_system else "",
                "realm_chain": power_system.get("typical_realm_chain", "") if power_system else "",
                "hard_limits": power_system.get("hard_limits", "") if power_system else ""
            },
            "villain": {
                "name": villain.get("name", "") if villain else "",
                "core_desire": villain.get("core_desire", "") if villain else "",
                "core_fear": villain.get("core_fear", "") if villain else "",
                "mirror_aspect": villain.get("shared_desire_flaw", "") if villain else ""
            },
            "core_constraints": core_constraints,
            "route": {
                "primary_genre": project.get("genre", ""),
                "secondary_genre": project.get("genre_label", "")
            },
            "writing_contract": {
                "style_guide": self._get_style_guide(project.get("genre", "")),
                "voice_tone": self._get_voice_tone(project.get("genre", "")),
                "pacing_rules": self._get_pacing_rules(project.get("genre", "")),
                "cool_point_requirements": self._get_cool_point_requirements(project.get("genre", ""))
            }
        }

    def _generate_anti_patterns(self, project: Dict, idea_bank: Dict) -> Dict:
        """生成anti_patterns.json内容。"""
        genre = project.get("genre", "")
        anti_patterns = []

        anti_patterns.extend(self._get_genre_anti_patterns(genre))

        if idea_bank:
            constraints = idea_bank.get("constraints_inherited", {})
            if constraints.get("anti_trope"):
                anti_patterns.append({
                    "pattern": constraints["anti_trope"],
                    "severity": "high",
                    "category": "anti_trope",
                    "description": "违反反套路规则"
                })

        return {
            "project_title": project.get("title", ""),
            "primary_genre": genre,
            "anti_patterns": anti_patterns,
            "version": "1.0"
        }

    def _get_style_guide(self, genre: str) -> str:
        """根据题材获取风格指南。"""
        guides = {
            "修仙": "古风典雅，用词讲究，注重修炼境界的描写，战斗场面要有层次感",
            "玄幻": "气势恢宏，充满想象力，战斗场面要宏大，世界观要开阔",
            "都市": "贴近现实，语言流畅自然，注重细节描写，情感真实",
            "科幻": "逻辑严谨，科技感强，注重硬科幻元素的合理性",
            "悬疑": "节奏紧凑，悬念迭起，注重细节铺垫和逻辑推理",
            "历史": "尊重历史背景，语言风格贴合时代，注重考据",
            "古言": "古风优美，情感细腻，注重礼仪和文化细节",
            "现言": "语言现代，情感真挚，注重人物心理描写",
            "游戏": "充满激情，节奏明快，注重竞技场面和团队协作",
            "末世": "氛围压抑，注重生存细节，展示人性挣扎",
            "奇幻": "充满魔法元素，世界观独特，注重想象力",
            "系统流": "清晰展示系统界面，注重升级和任务完成的爽感",
            "无限流": "每个世界风格不同，注重多样化和新鲜感",
            "规则怪谈": "氛围诡异，注重规则解读和心理恐惧",
            "克苏鲁": "氛围压抑，注重未知恐惧和理智崩坏"
        }
        return guides.get(genre, "语言流畅，情节紧凑，注重读者体验")

    def _get_voice_tone(self, genre: str) -> str:
        """根据题材获取语气语调。"""
        tones = {
            "修仙": "沉稳大气，略带古风",
            "玄幻": "激昂热血，充满豪情",
            "都市": "轻松幽默，贴近生活",
            "科幻": "理性冷静，客观严谨",
            "悬疑": "紧张刺激，引人入胜",
            "历史": "庄重典雅，充满底蕴",
            "古言": "温婉细腻，情感丰富",
            "现言": "亲切自然，情感真挚",
            "游戏": "激情澎湃，充满活力",
            "末世": "沉重压抑，充满求生欲",
            "奇幻": "神秘奇幻，充满想象力",
            "系统流": "条理清晰，充满成就感",
            "无限流": "丰富多彩，充满新鲜感",
            "规则怪谈": "诡异神秘，充满未知",
            "克苏鲁": "压抑沉重，充满恐惧"
        }
        return tones.get(genre, "生动活泼，引人入胜")

    def _get_pacing_rules(self, genre: str) -> Dict:
        """根据题材获取节奏规则。"""
        rules = {
            "修仙": {"chapter_pace": "2000-2500字", "cool_point_interval": "3-5章", "climax_interval": "15-20章"},
            "玄幻": {"chapter_pace": "2000-2500字", "cool_point_interval": "2-4章", "climax_interval": "12-18章"},
            "都市": {"chapter_pace": "1500-2000字", "cool_point_interval": "4-6章", "climax_interval": "18-25章"},
            "科幻": {"chapter_pace": "2000-2500字", "cool_point_interval": "3-5章", "climax_interval": "15-20章"},
            "悬疑": {"chapter_pace": "1500-2000字", "cool_point_interval": "2-3章", "climax_interval": "10-15章"},
            "历史": {"chapter_pace": "2000-2500字", "cool_point_interval": "4-6章", "climax_interval": "20-25章"},
            "古言": {"chapter_pace": "1500-2000字", "cool_point_interval": "3-5章", "climax_interval": "15-20章"},
            "现言": {"chapter_pace": "1500-2000字", "cool_point_interval": "3-5章", "climax_interval": "15-20章"},
            "游戏": {"chapter_pace": "2000-2500字", "cool_point_interval": "2-3章", "climax_interval": "10-15章"},
            "末世": {"chapter_pace": "2000-2500字", "cool_point_interval": "2-4章", "climax_interval": "12-18章"},
            "奇幻": {"chapter_pace": "2000-2500字", "cool_point_interval": "3-5章", "climax_interval": "15-20章"},
            "系统流": {"chapter_pace": "2000-2500字", "cool_point_interval": "2-3章", "climax_interval": "10-15章"},
            "无限流": {"chapter_pace": "2000-2500字", "cool_point_interval": "2-3章", "climax_interval": "10-15章"},
            "规则怪谈": {"chapter_pace": "1500-2000字", "cool_point_interval": "1-2章", "climax_interval": "8-12章"},
            "克苏鲁": {"chapter_pace": "2000-2500字", "cool_point_interval": "3-5章", "climax_interval": "15-20章"}
        }
        return rules.get(genre, {"chapter_pace": "2000-2500字", "cool_point_interval": "3-5章", "climax_interval": "15-20章"})

    def _get_cool_point_requirements(self, genre: str) -> Dict:
        """根据题材获取爽点要求。"""
        requirements = {
            "修仙": {"types": ["突破", "打脸", "寻宝", "收徒"], "frequency": "高"},
            "玄幻": {"types": ["战斗", "升级", "打脸", "奇遇"], "frequency": "高"},
            "都市": {"types": ["打脸", "扮猪吃虎", "逆袭", "情感"], "frequency": "中"},
            "科幻": {"types": ["科技突破", "解谜", "战斗", "探索"], "frequency": "中"},
            "悬疑": {"types": ["解谜", "反转", "发现", "惊悚"], "frequency": "高"},
            "历史": {"types": ["权谋", "征战", "发明", "逆袭"], "frequency": "中"},
            "古言": {"types": ["宫斗", "权谋", "情感", "逆袭"], "frequency": "中"},
            "现言": {"types": ["情感", "逆袭", "打脸", "成长"], "frequency": "中"},
            "游戏": {"types": ["胜利", "逆袭", "配合", "成长"], "frequency": "高"},
            "末世": {"types": ["生存", "战斗", "升级", "团结"], "frequency": "高"},
            "奇幻": {"types": ["魔法", "冒险", "发现", "战斗"], "frequency": "中"},
            "系统流": {"types": ["升级", "任务", "奖励", "打脸"], "frequency": "高"},
            "无限流": {"types": ["挑战", "突破", "逆袭", "发现"], "frequency": "高"},
            "规则怪谈": {"types": ["解谜", "反转", "惊悚", "生存"], "frequency": "高"},
            "克苏鲁": {"types": ["发现", "恐惧", "疯狂", "解密"], "frequency": "中"}
        }
        return requirements.get(genre, {"types": ["战斗", "升级", "逆袭"], "frequency": "中"})

    def _get_genre_anti_patterns(self, genre: str) -> list:
        """获取题材特定的反套路模式。"""
        patterns = {
            "修仙": [
                {"pattern": "主角一上来就天赋异禀", "severity": "high", "category": "character"},
                {"pattern": "所有女角色都爱上主角", "severity": "medium", "category": "relationship"},
                {"pattern": "反派都是纯粹的坏人", "severity": "medium", "category": "villain"},
                {"pattern": "修炼资源来得太容易", "severity": "high", "category": "power"},
                {"pattern": "宗门都是等级森严的刻板印象", "severity": "low", "category": "world"}
            ],
            "玄幻": [
                {"pattern": "主角总是越级挑战毫无压力", "severity": "high", "category": "power"},
                {"pattern": "金手指无所不能", "severity": "high", "category": "golden_finger"},
                {"pattern": "势力划分只有正邪对立", "severity": "medium", "category": "world"},
                {"pattern": "主角一路打脸爽到底", "severity": "medium", "category": "plot"},
                {"pattern": "配角都是工具人", "severity": "medium", "category": "character"}
            ],
            "都市": [
                {"pattern": "主角拥有无尽财富后就失去目标", "severity": "high", "category": "character"},
                {"pattern": "所有美女都主动投怀送抱", "severity": "medium", "category": "relationship"},
                {"pattern": "反派都是脸谱化的坏人", "severity": "medium", "category": "villain"},
                {"pattern": "主角的能力毫无代价", "severity": "high", "category": "power"},
                {"pattern": "主角总是单打独斗", "severity": "low", "category": "plot"}
            ],
            "科幻": [
                {"pattern": "技术问题都靠主角一人解决", "severity": "medium", "category": "plot"},
                {"pattern": "人工智能总是无条件服从", "severity": "medium", "category": "world"},
                {"pattern": "外星文明总是邪恶或友好的极端", "severity": "medium", "category": "world"},
                {"pattern": "科技发展毫无代价", "severity": "high", "category": "theme"},
                {"pattern": "未来世界完美无瑕", "severity": "medium", "category": "world"}
            ],
            "悬疑": [
                {"pattern": "凶手总是最不可能的那个人", "severity": "medium", "category": "plot"},
                {"pattern": "主角总是智商在线", "severity": "medium", "category": "character"},
                {"pattern": "伏笔都能轻易回收", "severity": "low", "category": "plot"},
                {"pattern": "真相大白后一切圆满", "severity": "medium", "category": "theme"},
                {"pattern": "配角都是背景板", "severity": "medium", "category": "character"}
            ],
            "历史": [
                {"pattern": "主角改变历史后毫无副作用", "severity": "high", "category": "plot"},
                {"pattern": "历史人物都是脸谱化的", "severity": "medium", "category": "character"},
                {"pattern": "主角总是开金手指", "severity": "high", "category": "power"},
                {"pattern": "女性角色都是花瓶", "severity": "medium", "category": "character"},
                {"pattern": "历史事件都按主角意愿发展", "severity": "high", "category": "plot"}
            ],
            "古言": [
                {"pattern": "女主总是靠男人上位", "severity": "high", "category": "character"},
                {"pattern": "宫斗都是简单的陷害", "severity": "medium", "category": "plot"},
                {"pattern": "男主都是完美的", "severity": "medium", "category": "character"},
                {"pattern": "配角都是工具人", "severity": "medium", "category": "character"},
                {"pattern": "结局总是圆满的", "severity": "low", "category": "theme"}
            ],
            "现言": [
                {"pattern": "霸道总裁都是完美人设", "severity": "medium", "category": "character"},
                {"pattern": "女主总是傻白甜", "severity": "high", "category": "character"},
                {"pattern": "爱情解决一切问题", "severity": "medium", "category": "theme"},
                {"pattern": "配角都是助攻", "severity": "medium", "category": "character"},
                {"pattern": "婚姻是最终归宿", "severity": "low", "category": "theme"}
            ],
            "游戏": [
                {"pattern": "游戏技能都能带到现实", "severity": "high", "category": "power"},
                {"pattern": "主角在游戏中无敌", "severity": "high", "category": "power"},
                {"pattern": "队友都是工具人", "severity": "medium", "category": "character"},
                {"pattern": "游戏世界和现实完全割裂", "severity": "medium", "category": "world"},
                {"pattern": "电竞选手都是天才少年", "severity": "medium", "category": "character"}
            ],
            "末世": [
                {"pattern": "主角团队总是无敌的", "severity": "high", "category": "plot"},
                {"pattern": "人性在末世中只有恶", "severity": "medium", "category": "theme"},
                {"pattern": "变异都是有益的", "severity": "medium", "category": "world"},
                {"pattern": "重建文明太容易", "severity": "high", "category": "plot"},
                {"pattern": "反派都是纯粹的恶", "severity": "medium", "category": "villain"}
            ],
            "奇幻": [
                {"pattern": "魔法无所不能", "severity": "high", "category": "power"},
                {"pattern": "种族都是刻板印象", "severity": "medium", "category": "world"},
                {"pattern": "预言总是准确的", "severity": "medium", "category": "plot"},
                {"pattern": "英雄总是无私的", "severity": "medium", "category": "character"},
                {"pattern": "怪物都是纯粹的恶", "severity": "medium", "category": "world"}
            ],
            "系统流": [
                {"pattern": "系统任务总是轻松完成", "severity": "high", "category": "golden_finger"},
                {"pattern": "系统总是无条件帮助主角", "severity": "high", "category": "golden_finger"},
                {"pattern": "系统奖励总是正好需要的", "severity": "medium", "category": "golden_finger"},
                {"pattern": "主角完全依赖系统", "severity": "high", "category": "character"},
                {"pattern": "系统后期消失或升级就结束", "severity": "medium", "category": "plot"}
            ],
            "无限流": [
                {"pattern": "每个世界都是轻松通关", "severity": "high", "category": "plot"},
                {"pattern": "队友都是工具人", "severity": "medium", "category": "character"},
                {"pattern": "主角总是最强的", "severity": "high", "category": "power"},
                {"pattern": "世界之间毫无联系", "severity": "medium", "category": "world"},
                {"pattern": "最终目的都是回到现实", "severity": "medium", "category": "theme"}
            ],
            "规则怪谈": [
                {"pattern": "规则都能轻松破解", "severity": "high", "category": "plot"},
                {"pattern": "主角总是智商在线", "severity": "medium", "category": "character"},
                {"pattern": "怪谈都是纯粹的恐怖", "severity": "medium", "category": "theme"},
                {"pattern": "结局总是逃脱", "severity": "medium", "category": "theme"},
                {"pattern": "规则都是外部的", "severity": "low", "category": "theme"}
            ],
            "克苏鲁": [
                {"pattern": "主角总是理智的", "severity": "high", "category": "character"},
                {"pattern": "怪物总是直接出现", "severity": "medium", "category": "world"},
                {"pattern": "知识总是力量", "severity": "high", "category": "theme"},
                {"pattern": "主角总是英雄", "severity": "medium", "category": "character"},
                {"pattern": "真相总是能被理解", "severity": "medium", "category": "theme"}
            ]
        }
        return patterns.get(genre, [])

    def _parse_json_field(self, field: str) -> Any:
        """解析JSON字段。"""
        if not field:
            return []
        try:
            return json.loads(field)
        except json.JSONDecodeError:
            return []
