# -*- coding: utf-8 -*-
"""诊断报告生成：将一次运行渲染为自包含 HTML（内联样式，无外部依赖）。"""

import html
import json
import os
from typing import Any, Dict, List


def _esc(text: Any) -> str:
    return html.escape(str(text if text is not None else ""))


def _pre(text: Any, maxlen: int = 60000) -> str:
    s = str(text if text is not None else "")
    if len(s) > maxlen:
        s = s[:maxlen] + f"\n…[已截断 {len(str(text)) - maxlen} 字符]"
    return f"<pre>{_esc(s)}</pre>"


def build_report(recorder, summary: Dict[str, Any]) -> str:
    """生成 report.html 并返回路径。"""
    rows: List[str] = []
    for i, c in enumerate(recorder.calls, 1):
        decision = _esc(c.get("decision", ""))
        color = {"real": "#2ecc71", "replay": "#4da3ff", "skip": "#8fa0bd"}.get(decision, "#8fa0bd")
        rows.append(f"""
        <details style="border:1px solid #2a3550;border-radius:8px;margin:8px 0;background:#171e2e;">
          <summary style="padding:10px 14px;cursor:pointer;font-size:13.5px;">
            <span style="display:inline-block;width:64px;color:{color};font-weight:700;">{decision}</span>
            <b>{_esc(c.get('executor_name',''))}</b> / <code>{_esc(c.get('prompt_name',''))}</code>
            <span style="color:#8fa0bd;margin-left:12px;">model={_esc(c.get('model_name',''))}</span>
            <span style="color:#8fa0bd;margin-left:12px;">in={c.get('input_tokens',0)} out={c.get('output_tokens',0)}</span>
            <span style="color:#8fa0bd;margin-left:12px;">{c.get('latency_ms',0)}ms</span>
          </summary>
          <div style="padding:0 14px 12px;">
            <div style="font-size:12.5px;color:#8ec4ff;margin:6px 0 2px;">SYSTEM PROMPT</div>
            {_pre(c.get('system_prompt',''))}
            <div style="font-size:12.5px;color:#8ec4ff;margin:8px 0 2px;">USER PROMPT</div>
            {_pre(c.get('user_prompt',''))}
            <div style="font-size:12.5px;color:#8ec4ff;margin:8px 0 2px;">RAW OUTPUT</div>
            {_pre(c.get('raw_output',''))}
          </div>
        </details>""")

    step_rows = "".join(
        f"<tr><td>{_esc(s.get('step',''))}</td>"
        f"<td style='color:{'#2ecc71' if s.get('success') else '#e74c3c'}'>{'成功' if s.get('success') else '失败'}</td>"
        f"<td>{_esc(s.get('summary',''))}</td>"
        f"<td style='color:#ff8a80'>{_esc(s.get('error',''))}</td></tr>"
        for s in recorder.steps
    )

    diff_links = ""
    if summary.get("diff_files"):
        items = "".join(f"<li><code>{_esc(d)}</code></li>" for d in summary["diff_files"])
        diff_links = f"<h3>与上一次同 tag 运行对比</h3><ul>{items}</ul>"

    decision = summary.get("by_decision", {})
    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Prompt 诊断运行报告</title>
<style>
  body{{background:#0f1420;color:#dbe4f5;font-family:"Microsoft YaHei","PingFang SC",sans-serif;
        margin:0;padding:24px;line-height:1.6;}}
  .wrap{{max-width:1060px;margin:0 auto;}}
  h1{{font-size:22px;margin:0 0 4px;}}
  h2{{font-size:17px;border-left:4px solid #4da3ff;padding-left:10px;margin:26px 0 10px;}}
  h3{{font-size:14.5px;margin:14px 0 6px;color:#a8c6ff;}}
  .sub{{color:#8fa0bd;font-size:13px;margin-bottom:16px;}}
  .kpi{{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0;}}
  .kpi .box{{background:#171e2e;border:1px solid #2a3550;border-radius:8px;padding:10px 14px;min-width:130px;}}
  .kpi .num{{font-size:20px;font-weight:700;color:#4da3ff;}}
  .kpi .lbl{{font-size:12px;color:#8fa0bd;}}
  table{{width:100%;border-collapse:collapse;font-size:13px;}}
  th,td{{border:1px solid #2a3550;padding:6px 9px;text-align:left;vertical-align:top;}}
  th{{background:#1d2538;color:#b9cdf2;}}
  pre{{background:#0c111c;border:1px solid #2a3550;border-radius:6px;padding:10px;font-size:12px;
       color:#c6d4ec;white-space:pre-wrap;word-break:break-all;max-height:420px;overflow:auto;}}
  code{{background:#0c111c;border:1px solid #2a3550;border-radius:4px;padding:1px 5px;font-size:12px;}}
</style>
</head>
<body>
<div class="wrap">
<h1>Prompt 诊断运行报告</h1>
<div class="sub">script_id={_esc(summary.get('script_id',''))} · 第 {_esc(summary.get('chapter_index',''))} 章 ·
模式 {_esc(summary.get('mode',''))} · 生成于 {_esc(summary.get('generated_at',''))}</div>
<div class="kpi">
  <div class="box"><div class="num">{summary.get('llm_calls',0)}</div><div class="lbl">LLM 调用（real={decision.get('real',0)}/replay={decision.get('replay',0)}/skip={decision.get('skip',0)}）</div></div>
  <div class="box"><div class="num">{summary.get('tokens_in',0)}</div><div class="lbl">输入 tokens</div></div>
  <div class="box"><div class="num">{summary.get('tokens_out',0)}</div><div class="lbl">输出 tokens</div></div>
  <div class="box"><div class="num">{summary.get('elapsed_s',0)}s</div><div class="lbl">耗时</div></div>
  <div class="box"><div class="num">{summary.get('step_failures',0)}</div><div class="lbl">步骤失败</div></div>
</div>

<h2>步骤执行</h2>
<table><tr><th>步骤</th><th>状态</th><th>摘要</th><th>错误</th></tr>{step_rows}</table>

<h2>LLM 调用（{len(recorder.calls)}）</h2>
{''.join(rows) if rows else '<p style="color:#8fa0bd">本次运行无 LLM 调用。</p>'}

{diff_links}
</div>
</body>
</html>"""
    path = os.path.join(recorder.dir, "report.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    return path
