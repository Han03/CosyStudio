# -*- coding: utf-8 -*-
"""截断影响检查：成品末尾 / 剧情JSON完整性 / 各节点输出是否在目标区间。"""
import json
import re
import sqlite3

db = sqlite3.connect(r"C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db")
cur = db.cursor()

# 1. 成品末尾检查
with open(r"C:\MyProjects\CosyStudio\backend\tools\_e2e_polished.txt", encoding="utf-8") as f:
    polished = f.read()
print(f"== 成品 {len(polished)} 字（目标 800-1200）==")
print(f"  末尾 120 字: ...{polished[-120:]}")
# 判断是否自然收尾：最后一句是否以句号/引号/感叹号等结束
tail = polished[-50:]
ends = re.findall(r"[。！？…\"'」』”]|\.{2,}$", tail)
print(f"  末尾是否有结束标点: {bool(ends)} ({ends[-1] if ends else '无'})")
# 检查是否截断在句子中间：最后一句长度异常短且无标点
last_sent = re.split(r"[。！？\n]", tail)[-1].strip()
print(f"  最后一句: {last_sent!r}")

# 2. 剧情 JSON 完整性（#1192）
r = cur.execute("SELECT raw_output, parse_success, output_tokens FROM llm_call_logs WHERE id=1192").fetchone()
out, parse, tok = r[0] or "", r[1], r[2]
print(f"\n== chapter_plot #1192 parse={parse} output_tokens={tok} raw_output={len(out)}字符 ==")
print(f"  末尾 80 字: ...{out[-80:]}")
try:
    data = json.loads(re.sub(r"^```json\s*|\s*```$", "", out.strip()))
    print(f"  JSON 完整解析 OK，plots={len(data.get('plots', []))} 个")
    for i, p in enumerate(data["plots"], 1):
        d = p.get("description", "")
        print(f"    plot{i}: scene={p.get('scene', '')[:15]} desc={len(d)}字 emotion={p.get('emotion', '')[:12]}")
except Exception as e:
    print(f"  JSON 解析失败: {e}")

# 3. 各节点字数 vs 目标区间
print("\n== 各节点输出 vs 目标 ==")
checks = [
    (1192, "剧情生成", None),
    (1195, "剧情修订", None),
    (1197, "草稿", (400, 600)),
    (1200, "草稿修订", (400, 600)),
    (1202, "润色", (800, 1200)),
]
for pid, name, target in checks:
    r = cur.execute("SELECT raw_output, parse_success FROM llm_call_logs WHERE id=?", (pid,)).fetchone()
    raw = r[0] or ""
    parse = r[1]
    # 纯文本节点直接看字符；JSON 节点看解析后内容
    if parse:
        try:
            d = json.loads(re.sub(r"^```json\s*|\s*```$", "", raw.strip()))
            content = d.get("content", "") if isinstance(d, dict) and "content" in d else json.dumps(d, ensure_ascii=False)
            content = d.get("plots", []) if isinstance(d, dict) and "plots" in d else content
            if isinstance(content, list):
                content = json.dumps(content, ensure_ascii=False)
        except Exception:
            content = raw
        wc = len(content)
    else:
        wc = len(raw)
    in_range = f"{target[0]}<=ok<={target[1]}" if target and target[0] <= wc <= target[1] else "超限/不足" if target else "-"
    print(f"  #{pid} {name}: {wc} 字 (目标{target}) -> {in_range} parse={parse}")

db.close()
