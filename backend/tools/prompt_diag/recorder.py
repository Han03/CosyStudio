# -*- coding: utf-8 -*-
"""运行记录器：保存每次诊断运行的结果、统计与对比。

输出目录（默认 data/diag_runs/<script>/<chapter>/<tag>_<时间戳>/）：
    calls.jsonl    每次 LLM 调用一行（decision/executor/prompt/model/tokens/延迟/全文）
    steps.json     各步骤执行结果摘要
    summary.json   运行统计（真实/回放/跳过调用数、token、耗时）
    diff/          与上一次同 tag 运行的 prompt/输出文本 diff
    report.html    可视化报告
"""

import difflib
import json
import os
import time
from typing import Any, Dict, List, Optional


class RunRecorder:
    """单次诊断运行的结果记录。"""

    def __init__(
        self,
        script_id: int,
        chapter_index: int,
        runs_dir: Optional[str] = None,
        tag: Optional[str] = None,
    ):
        self.script_id = int(script_id)
        self.chapter_index = int(chapter_index)
        base = runs_dir or os.path.join("data", "diag_runs")
        ts = time.strftime("%Y%m%d_%H%M%S")
        tag_part = f"{tag}_" if tag else ""
        self.dir = os.path.join(
            base, str(self.script_id), str(self.chapter_index),
            f"{tag_part}{ts}",
        )
        os.makedirs(self.dir, exist_ok=True)
        self.calls: List[Dict[str, Any]] = []
        self.steps: List[Dict[str, Any]] = []
        self._call_fp = open(os.path.join(self.dir, "calls.jsonl"), "a", encoding="utf-8")
        self._started = time.time()

    # ------------------------------------------------------------------ 记录

    def record_call(self, **kwargs) -> None:
        call = dict(kwargs)
        self.calls.append(call)
        try:
            self._call_fp.write(json.dumps(call, ensure_ascii=False) + "\n")
            self._call_fp.flush()
        except Exception:
            pass

    def record_step(self, step_name: str, result) -> None:
        output = getattr(result, "output_data", None) or {}
        self.steps.append({
            "step": step_name,
            "success": bool(getattr(result, "success", False)),
            "summary": str(getattr(result, "step_summary", "") or ""),
            "error": str(getattr(result, "error_message", "") or ""),
            "output_keys": list(output.keys()) if isinstance(output, dict) else [],
            "ts": time.time(),
        })

    def record_step_error(self, step_name: str, exc: Exception) -> None:
        self.steps.append({
            "step": step_name,
            "success": False,
            "summary": "",
            "error": f"{type(exc).__name__}: {exc}",
            "output_keys": [],
            "ts": time.time(),
        })

    # ------------------------------------------------------------------ 汇总

    def summary(self) -> Dict[str, Any]:
        stats = {k: 0 for k in ("real", "replay", "skip")}
        tokens_in = tokens_out = 0
        latency = 0
        for c in self.calls:
            d = c.get("decision", "")
            if d in stats:
                stats[d] += 1
            tokens_in += int(c.get("input_tokens", 0) or 0)
            tokens_out += int(c.get("output_tokens", 0) or 0)
            latency += int(c.get("latency_ms", 0) or 0)
        return {
            "llm_calls": len(self.calls),
            "by_decision": stats,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms_total": latency,
            "elapsed_s": round(time.time() - self._started, 2),
            "steps": len(self.steps),
            "step_failures": sum(1 for s in self.steps if not s["success"]),
        }

    # ------------------------------------------------------------------ 落盘

    def finalize(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._call_fp.close()
        with open(os.path.join(self.dir, "steps.json"), "w", encoding="utf-8") as f:
            json.dump(self.steps, f, ensure_ascii=False, indent=2)
        summary = self.summary()
        if extra:
            summary.update(extra)
        with open(os.path.join(self.dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return summary

    # ------------------------------------------------------------------ diff

    def prev_run_dir(self, tag: str) -> Optional[str]:
        """返回同 tag 的上一运行目录（按时间戳取最近一个）。"""
        base_dir = os.path.dirname(self.dir)
        if not os.path.isdir(base_dir):
            return None
        candidates = [
            d for d in os.listdir(base_dir)
            if d.startswith(f"{tag}_")
            and os.path.isdir(os.path.join(base_dir, d))
            and os.path.abspath(os.path.join(base_dir, d)) != os.path.abspath(self.dir)
        ]
        candidates.sort()
        if not candidates:
            return None
        return os.path.join(base_dir, candidates[-1])

    def write_diffs(self, tag: Optional[str]) -> List[str]:
        """与上一次同 tag 运行对比，生成 prompt / 输出 diff 文件。"""
        if not tag:
            return []
        prev_dir = self.prev_run_dir(tag)
        if not prev_dir:
            return []
        prev_calls: List[Dict[str, Any]] = []
        prev_path = os.path.join(prev_dir, "calls.jsonl")
        if os.path.exists(prev_path):
            with open(prev_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        prev_calls.append(json.loads(line))
        if not prev_calls:
            return []
        diff_dir = os.path.join(self.dir, "diff")
        os.makedirs(diff_dir, exist_ok=True)
        written = []
        for i, cur in enumerate(self.calls):
            if i >= len(prev_calls):
                break
            prev = prev_calls[i]
            key = f"{i + 1:02d}_{cur.get('executor_name', '')}_{cur.get('prompt_name', '')}"
            sections = []
            for field, label in (("system_prompt", "system"), ("user_prompt", "user"), ("raw_output", "raw")):
                a = str(prev.get(field, ""))
                b = str(cur.get(field, ""))
                if a == b:
                    continue
                diff = "\n".join(difflib.unified_diff(
                    a.splitlines(), b.splitlines(),
                    fromfile=f"{label}@prev", tofile=f"{label}@cur", lineterm="",
                ))
                sections.append(f"--- {label} diff ---\n{diff}")
            if sections:
                path = os.path.join(diff_dir, f"{key}.diff")
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n\n".join(sections))
                written.append(os.path.basename(path))
        return written
