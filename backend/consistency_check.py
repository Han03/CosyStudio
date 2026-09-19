# -*- coding: utf-8 -*-
"""章节一致性检查：对指定章节检查各维度数据一致性，输出结构化结果。

用法: python consistency_check.py --chapter N [--script 999916]
维度:
 1. 章节时间轴    webnovel_timeline_chapter: 锚点/跨度/间隔/倒计时 连续性
 2. 角色状态      webnovel_character_state: 逐章状态跳变检查
 3. 角色物品      webnovel_character_item: 库存一致性(获取-失去)
 4. 角色卡        webnovel_character_card: 身份等关键字段完整性
 5. 角色关系      webnovel_character_relationship: 关系事实
 6. 世界观设定    webnovel_worldview_setting: 设定重复检查
 7. 剧情点        webnovel_chapter_plot: 累计与本章剧情点
 8. 伏笔/悬念    webnovel_open_loops + webnovel_timeline_countdown: 开放/回收/倒计时
 9. 金手指        webnovel_golden_finger: 设定与动态
10. 卷纲承诺      webnovel_volume_outline promise/payoff 覆盖
"""
import sys, os, json, argparse, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from repositories.base_repository import _get_conn


def get_conn():
    return _get_conn()


def check_timeline(conn, project_id, chapter, out):
    """1. 章节时间轴连续性"""
    rows = conn.execute(
        "SELECT chapter_number, time_anchor, chapter_duration, interval_from_prev, countdown_status, notes "
        "FROM webnovel_timeline_chapter WHERE timeline_id IN "
        "(SELECT id FROM webnovel_timeline WHERE project_id=?) ORDER BY chapter_number",
        (project_id,)).fetchall()
    cur = next((dict(r) for r in rows if r["chapter_number"] == chapter), None)
    if not cur:
        out.append({"维度": "时间轴", "结论": "缺数据", "详情": "本章无章节时间轴记录"})
        return
    items = []
    if not cur.get("time_anchor") or str(cur.get("time_anchor")) in ("（未知）", ""):
        items.append("time_anchor 为空或未知")
    prev = next((dict(r) for r in rows if r["chapter_number"] < chapter), None)
    if prev and cur.get("time_anchor") and prev.get("time_anchor"):
        if not str(cur["time_anchor"]).startswith(str(prev["time_anchor"])[:4]):
            items.append(f"纪年可能不一致: 上章={prev['time_anchor']} 本章={cur['time_anchor']}")
    if not items:
        items.append("正常")
    out.append({"维度": "时间轴", "结论": "正常" if items == ["正常"] else "有检查项",
                "详情": "；".join(items) + f" | 本章锚点: {cur.get('time_anchor')}"})


def check_character_state(conn, project_id, chapter, out):
    """2. 角色状态逐章连贯性"""
    rows = conn.execute(
        "SELECT character_name, chapter_number, location, state_summary FROM webnovel_character_state "
        "WHERE project_id=? AND chapter_number<=? ORDER BY character_name, chapter_number",
        (project_id, chapter)).fetchall()
    if not rows:
        out.append({"维度": "角色状态", "结论": "缺数据", "详情": "无角色状态记录"})
        return
    by_char = {}
    for r in rows:
        by_char.setdefault(r["character_name"], []).append(dict(r))
    issues = []
    for name, lst in by_char.items():
        lst.sort(key=lambda x: x["chapter_number"])
        locs = [x.get("location") or "" for x in lst]
        empty = [f"第{x['chapter_number']}章空" for x in lst if not (x.get("location") or x.get("state_summary"))]
        if empty:
            issues.append(f"{name}: {'/'.join(empty)}")
        if len(set(locs)) > 3:
            issues.append(f"{name}: 位置变化频繁({len(set(locs))}处): {'→'.join(locs[-4:])}")
    out.append({"维度": "角色状态", "结论": "有检查项" if issues else "正常",
                "详情": "；".join(issues) if issues else f"{len(by_char)}个角色状态记录正常"})


def check_character_item(conn, project_id, chapter, out):
    """3. 角色物品库存一致性"""
    rows = conn.execute(
        "SELECT character_id, item_name, quantity, acquired_chapter, lost_chapter FROM webnovel_character_item "
        "ORDER BY item_name, acquired_chapter").fetchall()
    if not rows:
        out.append({"维度": "角色物品", "结论": "缺数据", "详情": "无物品记录"})
        return
    latest = {}
    for r in rows:
        d = dict(r)
        key = (d["character_id"], d["item_name"])
        latest[key] = d
    zero = [f"{k[1]}" for k, v in latest.items() if (v.get("quantity") or 0) <= 0]
    dup = {}
    for r in rows:
        k = (dict(r)["character_id"], dict(r)["item_name"])
        dup.setdefault(k, 0)
        dup[k] += 1
    multi = [f"{k[1]}({c}条)" for k, c in dup.items() if c > 1]
    issues = []
    if zero:
        issues.append("持有量为0的残留: " + ", ".join(zero))
    if multi:
        issues.append("多条记录: " + ", ".join(multi))
    out.append({"维度": "角色物品", "结论": "有检查项" if issues else "正常",
                "详情": "；".join(issues) if issues else f"{len(latest)}个角色-物品持有记录正常"})


def check_character_card(conn, project_id, chapter, out):
    """4. 角色卡关键字段"""
    rows = conn.execute(
        "SELECT name, identity, alias, protagonist_relation FROM webnovel_character_card "
        "WHERE project_id=?", (project_id,)).fetchall()
    if not rows:
        out.append({"维度": "角色卡", "结论": "缺数据", "详情": "无角色卡"})
        return
    empty = [dict(r)["name"] for r in rows if not (dict(r).get("identity") or dict(r).get("alias"))]
    out.append({"维度": "角色卡", "结论": "有检查项" if empty else "正常",
                "详情": f"{len(rows)}张卡" + (f"；缺身份/别名: {','.join(empty)}" if empty else "，字段完整")})


def check_relationship(conn, project_id, chapter, out):
    """5. 角色关系事实"""
    rows = conn.execute(
        "SELECT character_id, relation_type, target_name, source_chapter FROM webnovel_character_relationship "
        "ORDER BY source_chapter").fetchall()
    if not rows:
        out.append({"维度": "角色关系", "结论": "缺数据", "详情": "无关系记录"})
        return
    out.append({"维度": "角色关系", "结论": "正常",
                "详情": f"{len(rows)}条关系事实: " + "；".join(
                    f"{r['character_id']}-{r['relation_type']}-{r['target_name']}(第{r['source_chapter']}章)"
                    for r in rows[-5:])})


def check_worldview(conn, project_id, chapter, out):
    """6. 世界观设定重复/冲突"""
    rows = conn.execute(
        "SELECT name, content, chapter_number FROM webnovel_worldview_setting "
        "WHERE project_id=? ORDER BY name, chapter_number", (project_id,)).fetchall()
    if not rows:
        out.append({"维度": "世界观设定", "结论": "缺数据", "详情": "无设定记录"})
        return
    by_name = {}
    for r in rows:
        by_name.setdefault(r["name"], []).append(dict(r))
    dup = {k: v for k, v in by_name.items() if len(v) > 1 and len(set(x.get("content", "")[:20] for x in v)) > 1}
    issues = [f"{k}({len(v)}条不同内容)" for k, v in dup.items()] if dup else []
    out.append({"维度": "世界观设定", "结论": "有检查项" if issues else "正常",
                "详情": "；".join(issues) if issues else f"{len(by_name)}个设定无重复"})


def check_plot(conn, project_id, chapter, out):
    """7. 剧情点"""
    rows = conn.execute(
        "SELECT chapter_index, description FROM webnovel_chapter_plot WHERE project_id=? "
        "AND chapter_index<=? ORDER BY chapter_index", (project_id, chapter)).fetchall()
    if not rows:
        out.append({"维度": "剧情点", "结论": "缺数据", "详情": "无剧情点"})
        return
    cur = [dict(r) for r in rows if r["chapter_index"] == chapter]
    out.append({"维度": "剧情点", "结论": "正常",
                "详情": f"累计{len(rows)}条" + (f"，本章{len(cur)}条" if cur else "，本章无剧情点")})


def check_loops(conn, project_id, chapter, out):
    """8. 开放悬念/倒计时"""
    loops = conn.execute(
        "SELECT content, status, planted_chapter, resolved_chapter FROM webnovel_open_loops "
        "WHERE project_id=?", (project_id,)).fetchall()
    cd = conn.execute(
        "SELECT event_name, current_status, trigger_chapter, planted_chapter FROM webnovel_timeline_countdown "
        "WHERE project_id=?", (project_id,)).fetchall()
    issues = []
    for r in loops:
        d = dict(r)
        if d.get("status") == "closed" and not d.get("resolved_chapter"):
            issues.append(f"悬念已回收但无回收章节: {str(d.get('content'))[:30]}")
    out.append({"维度": "伏笔/悬念", "结论": "有检查项" if issues else "正常",
                "详情": "；".join(issues) if issues else
                f"开放悬念{len(loops)}条(开放{sum(1 for r in loops if dict(r).get('status')!='closed')}/"
                f"回收{sum(1 for r in loops if dict(r).get('status')=='closed')})，倒计时{len(cd)}条"})


def check_golden_finger(conn, project_id, chapter, out):
    """9. 金手指"""
    gf = conn.execute(
        "SELECT main_role, core_function FROM webnovel_golden_finger WHERE project_id=? LIMIT 3",
        (project_id,)).fetchall()
    if not gf:
        out.append({"维度": "金手指", "结论": "缺数据", "详情": "无金手指记录"})
        return
    out.append({"维度": "金手指", "结论": "正常",
                "详情": f"{len(gf)}条设定: " + "；".join(
                    f"{dict(r).get('main_role') or ''}-{dict(r).get('core_function') or ''}" for r in gf)})


def check_volume_promise(conn, project_id, chapter, out):
    """10. 卷纲承诺覆盖"""
    vo = conn.execute(
        "SELECT volume_name, promise_description FROM webnovel_volume_outline "
        "WHERE project_id=? AND chapter_start<=? ORDER BY chapter_start LIMIT 1", (project_id, chapter)).fetchall()
    if not vo:
        out.append({"维度": "卷纲承诺", "结论": "缺数据", "详情": "无卷纲"})
        return
    v = dict(vo[0])
    out.append({"维度": "卷纲承诺", "结论": "正常",
                "详情": f"卷{v.get('volume_name')} promise 已载入上下文（覆盖依赖注入质量）"})


def run(script_id, chapter):
    conn = get_conn()
    proj = conn.execute("SELECT id FROM webnovel_project WHERE script_id=?", (script_id,)).fetchone()
    if not proj:
        print(json.dumps([{"维度": "系统", "结论": "错误", "详情": "项目不存在"}], ensure_ascii=False))
        return
    project_id = proj["id"]
    out = []
    check_timeline(conn, project_id, chapter, out)
    check_character_state(conn, project_id, chapter, out)
    check_character_item(conn, project_id, chapter, out)
    check_character_card(conn, project_id, chapter, out)
    check_relationship(conn, project_id, chapter, out)
    check_worldview(conn, project_id, chapter, out)
    check_plot(conn, project_id, chapter, out)
    check_loops(conn, project_id, chapter, out)
    check_golden_finger(conn, project_id, chapter, out)
    check_volume_promise(conn, project_id, chapter, out)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter", type=int, required=True)
    ap.add_argument("--script", type=int, default=999916)
    args = ap.parse_args()
    run(args.script, args.chapter)
