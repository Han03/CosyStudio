# -*- coding: utf-8 -*-
"""验证：剧情列表注入不再用【】包裹场景名，改用「」"""
import sys, json
sys.path.insert(0, r"C:\MyProjects\CosyStudio\backend")

from webnovel.pipeline.resource_registry import _fmt_plot_list

plot_list = [
    {"scene": "破庙门口", "description": "李威发现敌情，示意众人戒备", "characters": ["李威", "林天昊"], "emotion": "警惕→紧张", "conflict": "敌军逼近"},
    {"scene": "庙内", "description": "众人转移伤员", "characters": ["苏婉清"], "emotion": "紧张→稍缓", "conflict": ""},
]
out = _fmt_plot_list(plot_list)
print(out)
assert "【" not in out, "仍含【】包裹的场景名"
assert "「" in out, "未使用「」"
print("\n[OK] 剧情列表场景名已改用「」，与区块标题【】体系区分")
