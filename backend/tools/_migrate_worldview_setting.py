# 一次性迁移：拆分 webnovel_worldview.world_summary 中的【第N章·分类】追加块 → webnovel_worldview_setting
# 迁移后 world_summary 仅保留初始化总纲。可重复执行（幂等）。
import re
import sqlite3

DB = r'C:\MyProjects\CosyStudio\data\cache\app.db'
PATTERN = re.compile(r'【第(\d+)章·([^】]+)】\s*([^【\n]+(?:\n(?!【第\d+章·)[^【\n]*)*)', re.M)


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute('SELECT id, project_id, world_summary FROM webnovel_worldview')
    rows = cur.fetchall()
    total = 0
    for row in rows:
        wid, pid, summary = row["id"], row["project_id"], row["world_summary"] or ""
        if '【第' not in summary:
            continue
        # 收集匹配块
        matches = list(PATTERN.finditer(summary))
        if not matches:
            continue
        clean_parts = []
        last_end = 0
        migrated = 0
        for m in matches:
            ch = int(m.group(1))
            category = m.group(2).strip()
            body = m.group(3).strip()
            # 解析 name：内容首行冒号前为 name，否则整段为 name
            lines = body.split('\n')
            first = lines[0].strip()
            if '：' in first or ':' in first:
                name, _, rest = first.partition('：') if '：' in first else first.partition(':')
                name = name.strip()
                content = (rest + '\n' + '\n'.join(lines[1:])).strip()
            else:
                name = first
                content = '\n'.join(lines[1:]).strip() or first
            if not name or not content:
                # 只有一行时 name 即内容
                if first:
                    name, content = first, first
                else:
                    continue
            # 迁移到新表（幂等：按 project+chapter+name 查重）
            dup = cur.execute(
                """SELECT id FROM webnovel_worldview_setting
                   WHERE project_id = ? AND chapter_number = ? AND name = ?""",
                (pid, ch, name)
            ).fetchone()
            if not dup:
                cur.execute(
                    """INSERT INTO webnovel_worldview_setting
                       (project_id, chapter_number, name, content, category)
                       VALUES (?, ?, ?, ?, ?)""",
                    (pid, ch, name, content[:600], category)
                )
                migrated += 1
                total += 1
            clean_parts.append(summary[last_end:m.start()])
            last_end = m.end()
        # 保留块间文本（若有）
        clean_parts.append(summary[last_end:])
        clean = ''.join(clean_parts).strip()
        # 若全部为块构成，清理后可能只剩空；保留总纲部分
        if clean != summary:
            cur.execute(
                'UPDATE webnovel_worldview SET world_summary = ? WHERE id = ?',
                (clean, wid)
            )
        print(f'[project {pid}] 迁移 {migrated} 条，world_summary {len(summary)} → {len(clean)} 字符')

    conn.commit()
    conn.close()
    print(f'迁移完成，共 {total} 条')


if __name__ == '__main__':
    main()
