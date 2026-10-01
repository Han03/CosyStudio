# -*- coding: utf-8 -*-
"""智能创作第1章后：write 落库数据 + LLM 调用统计 + 正文质量抽样检查。"""
import sys, sqlite3
sys.stdout.reconfigure(encoding='utf-8')

DB = r'C:\MyProjects\CosyStudio\data\cache\app.db'
LOGDB = r'C:\MyProjects\CosyStudio\data\cache\app_llm_logs.db'
PID = 102

def q(sql, args=(), db=DB):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute(sql, args)
    rows = cur.fetchall()
    conn.close()
    return rows

print('===== 智能创作第1章 · 落库数据检查 =====')

# 1. 剧情点
rows = q(f'SELECT plot_order, scene, characters, conflict FROM webnovel_chapter_plot WHERE project_id={PID} AND chapter_index=1 ORDER BY plot_order')
print(f'\n[1] webnovel_chapter_plot: {len(rows)} 个剧情点')
for r in rows:
    print(f'   {r[0]:>2}. 【{r[1]}】角色:{r[2][:40]} 冲突:{str(r[3])[:40]}')

# 2. 章节规划
rows = q(f'SELECT chapter_title, summary, key_events, chapter_hook, chapter_goal FROM webnovel_chapter_plan WHERE chapter_index=1')
print(f'\n[2] webnovel_chapter_plan 第1章: {len(rows)} 条')
for r in rows:
    print(f'   标题: {r[0]}')
    print(f'   summary: {str(r[1])[:80]}')
    print(f'   key_events: {str(r[2])[:80]}')
    print(f'   章节钩子: {str(r[3])[:60]}')
    print(f'   章节目标: {str(r[4])[:60]}')

# 3. 卷危机（拆章补全产物）
rows = q(f'SELECT id, crisis_order, crisis_event, cost_risk_upgrade FROM webnovel_volume_crisis WHERE volume_outline_id=278 ORDER BY crisis_order')
print(f'\n[3] webnovel_volume_crisis(卷1, 补全后): {len(rows)} 条')
for r in rows:
    print(f'   #{r[1]} {str(r[2])[:60]}')
    print(f'      代价升级: {str(r[3])[:50]}')

# 4. writing_task（创作产物）
rows = q(f"SELECT id, status, length(draft), length(polished), progress_message FROM script_writing_tasks WHERE script_id=999916 AND chapter_index=1 ORDER BY id DESC LIMIT 1")
print(f'\n[4] script_writing_tasks 最新任务: id={rows[0][0]} status={rows[0][1]} draft={rows[0][2]}字 polished={rows[0][3]}字 msg={rows[0][4]}')
if rows:
    row2 = q(f'SELECT polished FROM script_writing_tasks WHERE id={rows[0][0]}')[0]
    polished = row2[0] or ''
    print(f'   润色正文 {len(polished)} 字，前 400 字:')
    print('   ' + polished[:400].replace(chr(10), '⏎'))

# 5. LLM 调用统计（本次创作 id 263-276）
rows = q("""SELECT prompt_name, COUNT(*), ROUND(AVG(latency_ms)), SUM(input_tokens), SUM(output_tokens)
            FROM llm_call_logs WHERE id BETWEEN 263 AND 276
            GROUP BY prompt_name ORDER BY MIN(id)""", db=LOGDB)
print(f'\n[5] LLM 调用统计 (id 263-276, 共{sum(r[1] for r in rows)}条):')
total_tok = 0
for r in rows:
    print(f'   {r[0]:<28} x{r[1]}  均耗{r[2]}ms  in={r[3]} out={r[4]}')
    total_tok += (r[3] or 0) + (r[4] or 0)
print(f'   总 token: {total_tok}')

# 6. 未落库说明
print('\n[6] 说明：正文/章节meta/角色状态/时间轴/伏笔等表由【应用结果】阶段落库，本次仅执行了智能创作(write)流程。')
