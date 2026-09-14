# -*- coding: utf-8 -*-
"""步骤7探针：解析函数单测 + agents.json/config 全量路径存在性 + find_* 有效。"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, r'C:\MyProjects\CosyStudio\backend')
from core.paths import resolve_project_path, to_project_relpath, PROJECT_ROOT

fails = []

def check(name, cond):
    print(f'  {"PASS" if cond else "FAIL"}: {name}')
    if not cond:
        fails.append(name)

print('== resolve_project_path 单测 ==')
# 相对路径
p1 = resolve_project_path('pretrained_models/cosyvoice/CosyVoice3-0.5B-2512')
check(f'相对→绝对存在: {p1}', os.path.isdir(p1))
# 旧绝对路径重组（容错）
old_abs = r'C:\MyProjects\ai\CosyStudio\pretrained_models\cosyvoice\CosyVoice3-0.5B-2512'
p2 = resolve_project_path(old_abs)
check(f'旧绝对→重组: {p2}', p2 == os.path.join(PROJECT_ROOT, 'pretrained_models', 'cosyvoice', 'CosyVoice3-0.5B-2512'))
# 不存在的绝对路径原样
p3 = resolve_project_path(r'D:\nonexistent\path')
check(f'不存在绝对→原样: {p3}', p3 == r'D:\nonexistent\path')
# URL 原样
p4 = resolve_project_path('https://x.com/a')
check(f'URL→原样: {p4}', p4 == 'https://x.com/a')
# 空
check('空→空', resolve_project_path('') == '')

print('== to_project_relpath 往返 ==')
rel = to_project_relpath(os.path.join(PROJECT_ROOT, 'data', 'agents', 'x', 'tones', 'a.wav'))
check(f'往返: {rel}', rel == 'data/agents/x/tones/a.wav' and resolve_project_path(rel).endswith('data\\agents\\x\\tones\\a.wav'))
check('项目外原样', to_project_relpath(r'D:\outside\x') == r'D:\outside\x')

print('== agents.json 全量路径 ==')
agents = json.load(open(r'C:\MyProjects\CosyStudio\data\agents\agents.json', encoding='utf-8'))
lst = agents if isinstance(agents, list) else agents.get('agents', [])
total, missing = 0, 0
for a in lst:
    for vt in a.get('voice_tones', []):
        for k in ('voice_path', 'original_path'):
            v = vt.get(k)
            if v:
                total += 1
                if not os.path.exists(resolve_project_path(v)):
                    missing += 1
                    print(f'    MISSING {k}: {v}')
    for k in ('voice_path', 'original_path'):
        v = a.get(k)
        if v and 'tones' in v:
            total += 1
            if not os.path.exists(resolve_project_path(v)):
                missing += 1
check(f'agents.json {total} 条存在（缺失 {missing}）', missing == 0 and total >= 75)

print('== config 5 模型路径 ==')
cfg = json.load(open(r'C:\MyProjects\CosyStudio\config\system_config.json', encoding='utf-8'))
for name, m in cfg['models'].items():
    v = m.get('model_path', '')
    if v:
        rp = resolve_project_path(v)
        check(f'{name}: {v} → {rp}', os.path.isdir(rp))

print('== find_* 有效 ==')
from core import model_manager
for fn, label in ((model_manager.find_cosyvoice_model, 'cosyvoice'),
                  (model_manager.find_qwen_model, 'qwen'),
                  (model_manager.find_dreamlite_model, 'dreamlite')):
    p = fn()
    check(f'{label}: {p}', bool(p) and os.path.isdir(p))

print()
print('全部通过' if not fails else f'失败 {len(fails)} 项: {fails}')
sys.exit(1 if fails else 0)
