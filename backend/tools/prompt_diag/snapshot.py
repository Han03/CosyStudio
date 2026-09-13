# -*- coding: utf-8 -*-
"""快照仓库：保存 / 读取诊断基准快照。

目录结构（默认 data/diag_snapshots/<script_id>/<chapter>/）：
    manifest.json   元信息（script/chapter/mode/生成时间/DB 指纹/调用数）
    calls.jsonl     基准运行的完整 LLM 调用记录（按顺序，供 REPLAY）
    steps.json      各步骤 output_data（信息记录，供对比）
"""

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional


class SnapshotStore:
    """诊断基准快照的读写。"""

    def __init__(self, script_id: int, chapter_index: int, snapshot_dir: Optional[str] = None):
        self.script_id = int(script_id)
        self.chapter_index = int(chapter_index)
        if snapshot_dir:
            self.base = snapshot_dir
        else:
            self.base = os.path.join(
                "data", "diag_snapshots",
                str(self.script_id), str(self.chapter_index),
            )
        self._calls: Optional[List[Dict[str, Any]]] = None
        self.manifest: Dict[str, Any] = {}

    # ------------------------------------------------------------------ 路径

    def _path(self, name: str) -> str:
        return os.path.join(self.base, name)

    def exists(self) -> bool:
        return os.path.exists(self._path("manifest.json"))

    # ------------------------------------------------------------------ 保存

    def save(
        self,
        meta: Dict[str, Any],
        calls: List[Dict[str, Any]],
        steps: Dict[str, Any],
    ) -> str:
        os.makedirs(self.base, exist_ok=True)
        manifest = dict(meta)
        manifest.setdefault("created_at", time.time())
        manifest["llm_calls"] = len(calls)
        with open(self._path("manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        with open(self._path("calls.jsonl"), "w", encoding="utf-8") as f:
            for c in calls:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        with open(self._path("steps.json"), "w", encoding="utf-8") as f:
            json.dump(steps, f, ensure_ascii=False, indent=2)
        self.manifest = manifest
        return self.base

    # ------------------------------------------------------------------ 加载

    def load(self) -> "SnapshotStore":
        if not self.exists():
            raise FileNotFoundError(f"快照不存在：{self.base}")
        with open(self._path("manifest.json"), "r", encoding="utf-8") as f:
            self.manifest = json.load(f)
        self._calls = []
        with open(self._path("calls.jsonl"), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._calls.append(json.loads(line))
        return self

    def calls_by(self, executor_name: str, prompt_name: str) -> List[Dict[str, Any]]:
        if self._calls is None:
            self.load()
        return [
            c for c in self._calls
            if c.get("executor_name") == executor_name and c.get("prompt_name") == prompt_name
        ]

    def load_steps(self) -> Dict[str, Any]:
        try:
            with open(self._path("steps.json"), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    # ------------------------------------------------------------------ DB 指纹

    def db_fingerprint(self, project_id: int) -> str:
        """基于关键数据规模计算 DB 指纹，用于提示快照过期。"""
        parts = []
        try:
            from webnovel.repositories import (
                get_character_cards_by_project,
                get_active_open_loops,
                get_all_chapter_plans_for_project,
                get_chapter_plot,
            )
            chars = get_character_cards_by_project(project_id) or []
            loops = get_active_open_loops(project_id) or []
            plans = get_all_chapter_plans_for_project(project_id) or []
            plot = get_chapter_plot(project_id, self.chapter_index) or {}
            parts = [
                f"chars={len(chars)}",
                f"loops={len(loops)}",
                f"plans={len(plans)}",
                f"plan_hash={hashlib.md5(json.dumps(plans, ensure_ascii=False).encode('utf-8')).hexdigest()[:8]}",
                f"plot={bool(plot)}",
            ]
        except Exception:
            parts = ["fp=unknown"]
        return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:12]

    def fingerprint_changed(self, project_id: int) -> bool:
        fp = self.db_fingerprint(project_id)
        old = self.manifest.get("db_fingerprint", "")
        return bool(old) and old != fp
