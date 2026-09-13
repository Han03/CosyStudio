# -*- coding: utf-8 -*-
"""全流程诊断记录器：把每一步的 LLM 调用、执行器步骤、DB 入库按事件流写入独立目录。

产物目录（每次运行一个独立文件夹）：
  backend/data/pipeline_diag_runs/<script_id>/<chapter>/<tag>_<ts>/
    meta.json        运行元信息（剧本/章节/起止/耗时/参数）
    llm_calls.jsonl  每次 LLM 调用：system/user prompt、输出、tokens、耗时、所属步骤
    steps.jsonl      每个执行器步骤：名称、耗时、成功与否、期间的 LLM/DB 事件区间
    db_writes.jsonl  每次 DB 写（INSERT/UPDATE/DELETE/REPLACE）：表名、SQL、参数、所属步骤
    events.jsonl     阶段标记（writing/apply 等）时间线
    summary.json     汇总：按 executor|prompt 统计、按表统计写次数、步骤清单
"""

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SQL_TABLE_RE = re.compile(
    r"(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|UPDATE|DELETE\s+FROM|REPLACE\s+INTO)\s+([`\"\[]?[\w.]+[`\"\]]?)",
    re.IGNORECASE,
)

_SKIP_SQL_RE = re.compile(
    r"^\s*(SELECT|PRAGMA|BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE|CREATE|ALTER|DROP|VACUUM|ANALYZE)",
    re.IGNORECASE,
)


def _fmt_param(value: Any, max_len: int = 400) -> Any:
    """参数安全序列化：超长截断，bytes 转可读。"""
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return f"<bytes {len(value)}B>"
    if isinstance(value, (list, tuple, dict)):
        try:
            s = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            s = str(value)
        if len(s) > max_len:
            return s[:max_len] + f"...<truncated {len(s)} chars>"
        return s
    s = str(value)
    if len(s) > max_len:
        return s[:max_len] + f"...<truncated {len(s)} chars>"
    return s


def _extract_table(sql: str) -> str:
    m = _SQL_TABLE_RE.search(sql)
    if not m:
        return ""
    return m.group(1).strip("`\"[]")


class PipelineDiagRecorder:
    """事件流记录器（线程安全：写文件用锁）。"""

    def __init__(self, script_id: int, chapter_index: int, tag: str = "diag",
                 runs_root: Optional[str] = None):
        base = runs_root or os.path.join(_BACKEND_ROOT, "data", "pipeline_diag_runs")
        stamp = time.strftime("%Y%m%d_%H%M%S")
        name = f"{tag}_{stamp}" if tag else stamp
        self.dir = os.path.join(base, str(script_id), str(chapter_index), name)
        os.makedirs(self.dir, exist_ok=True)

        self.script_id = script_id
        self.chapter_index = chapter_index
        self.tag = tag
        self.start_time = time.time()
        self.end_time: Optional[float] = None

        self._lock = __import__("threading").RLock()
        self._seq = 0
        self._db_seq = 0
        self._stage = "init"
        self._current_step = ""

        self._f_llm = open(os.path.join(self.dir, "llm_calls.jsonl"), "w", encoding="utf-8")
        self._f_steps = open(os.path.join(self.dir, "steps.jsonl"), "w", encoding="utf-8")
        self._f_db = open(os.path.join(self.dir, "db_writes.jsonl"), "w", encoding="utf-8")
        self._f_events = open(os.path.join(self.dir, "events.jsonl"), "w", encoding="utf-8")

        self.stats: Dict[str, Any] = {
            "llm_by_executor": {},      # key: "executor|prompt_name" -> {count,in_tok,out_tok,latency_ms,errors}
            "db_by_table": {},           # 表名 -> {count}
            "steps": [],                 # 步骤列表
            "errors": [],                # 异常记录
        }
        self.llm_seqs: List[int] = []   # 当前步骤期间 LLM 序号区间（由步骤包装器读写）
        self.db_seqs: List[int] = []
        self._active_llm_seq: Optional[int] = None

    # ------------------------------------------------------------------ 基础
    def _next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def _write(self, f, rec: Dict[str, Any]):
        with self._lock:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            f.flush()

    def _write_events(self, rec: Dict[str, Any]):
        rec.setdefault("ts", round(time.time(), 3))
        self._write(self._f_events, rec)

    # ------------------------------------------------------------------ 阶段/步骤
    def mark_stage(self, stage: str):
        self._stage = stage
        self._write_events({"type": "stage", "stage": stage})

    def set_step(self, name: str):
        self._current_step = name
        self.llm_seqs = []
        self.db_seqs = []

    def clear_step(self):
        self._current_step = ""

    # ------------------------------------------------------------------ LLM 调用
    def record_llm_call(self, data: Dict[str, Any]):
        seq = self._next_seq()
        rec = {
            "seq": seq,
            "ts": round(time.time(), 3),
            "stage": self._stage,
            "step": self._current_step,
            **data,
        }
        self._write(self._f_llm, rec)
        key = f"{rec.get('executor_name', '')}|{rec.get('prompt_name', '')}"
        st = self.stats["llm_by_executor"].setdefault(key, {
            "count": 0, "in_tok": 0, "out_tok": 0, "latency_ms": 0, "errors": 0,
        })
        st["count"] += 1
        st["in_tok"] += int(rec.get("input_tokens") or 0)
        st["out_tok"] += int(rec.get("output_tokens") or 0)
        st["latency_ms"] += int(rec.get("latency_ms") or 0)
        if rec.get("error"):
            st["errors"] += 1
        with self._lock:
            self.llm_seqs.append(seq)
            self._active_llm_seq = seq
        return seq

    # ------------------------------------------------------------------ DB 写
    def record_db_write(self, sql: str, params: Any):
        db_seq = self._db_seq + 1
        self._db_seq = db_seq
        table = _extract_table(sql)
        params_safe = None
        if isinstance(params, (list, tuple)):
            params_safe = [_fmt_param(p) for p in params]
        elif isinstance(params, dict):
            params_safe = {k: _fmt_param(v) for k, v in params.items()}
        rec = {
            "db_seq": db_seq,
            "ts": round(time.time(), 3),
            "stage": self._stage,
            "step": self._current_step,
            "llm_seq": self._active_llm_seq,
            "table": table,
            "sql": sql.strip(),
            "params": params_safe,
        }
        self._write(self._f_db, rec)
        with self._lock:
            self.db_seqs.append(db_seq)
        if table:
            st = self.stats["db_by_table"].setdefault(table, {"count": 0})
            st["count"] += 1
        return db_seq

    # ------------------------------------------------------------------ 步骤
    def record_step(self, name: str, started: float, ended: float,
                    success: bool, error: str = "", summary: str = "",
                    llm_seqs: Optional[List[int]] = None,
                    db_seqs: Optional[List[int]] = None):
        rec = {
            "step": name,
            "ts": round(started, 3),
            "elapsed_s": round(ended - started, 3),
            "success": success,
            "error": error or "",
            "summary": summary or "",
            "llm_seqs": llm_seqs or [],
            "db_seqs": db_seqs or [],
        }
        self._write(self._f_steps, rec)
        self.stats["steps"].append(rec)

    def record_error(self, where: str, exc: Exception):
        rec = {"where": where, "error": f"{type(exc).__name__}: {exc}"}
        self._write_events({"type": "error", **rec})
        self.stats["errors"].append(rec)

    # ------------------------------------------------------------------ 汇总
    def finalize(self, extra_meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.end_time is None:
            self.end_time = time.time()
        elapsed = round(self.end_time - self.start_time, 2)

        meta = {
            "script_id": self.script_id,
            "chapter_index": self.chapter_index,
            "tag": self.tag,
            "start_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.start_time)),
            "end_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.end_time)),
            "elapsed_s": elapsed,
            "run_dir": self.dir,
        }
        if extra_meta:
            meta.update(extra_meta)
        with self._lock:
            with open(os.path.join(self.dir, "meta.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            with open(os.path.join(self.dir, "summary.json"), "w", encoding="utf-8") as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
            for f in (self._f_llm, self._f_steps, self._f_db, self._f_events):
                try:
                    f.close()
                except Exception:
                    pass
        return {"meta": meta, "stats": self.stats}
