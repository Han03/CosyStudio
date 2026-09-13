# -*- coding: utf-8 -*-
"""诊断运行器：编排流水线步骤、注入调用策略、生成快照与运行记录。

运行模型：
- 快照缺失（且未 --fresh）→ 报错提示先生成快照（避免意外真实调用）。
- --fresh / --with-create → 全量真实调用，并（--fresh）保存基准快照。
- 默认（--only-context）→ 仅 context_analyzer 真实调用，其余节点快照回放。
- --node X → 节点 X（及内部上下文分析）真实调用，其余回放。

副作用隔离：默认将 executor 模块中的写库函数替换为 no-op
（add_chapter_plot / add_worldview），--commit 时才放行写生产表。
"""

import importlib
import os
import sys
import time
from typing import Any, Dict, List, Optional, Set

# 确保 backend 根目录可导入（独立脚本入口时生效）
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from tools.prompt_diag.policy import CallPolicy, DiagnosticModelExecutor, DiagSnapshotError
from tools.prompt_diag.recorder import RunRecorder
from tools.prompt_diag.snapshot import SnapshotStore

# ---------------------------------------------------------------------------
# 节点 → executor_name 映射（与 executor 内部传参一致）
# ---------------------------------------------------------------------------

NODE_EXECUTOR_NAMES: Dict[str, Set[str]] = {
    "context_analyzer": {"context_analyzer"},
    "chapter_plot_generator": {"chapter_plot_generator"},
    "chapter_plot_reviewer": {"chapter_plot_reviewer_score", "chapter_plot_reviewer_revise"},
    "chapter_plot_reviewer_revise": {"chapter_plot_reviewer_revise"},
    "draft_generator": {"draft_generator"},
    "draft_reviewer": {"draft_reviewer_score", "draft_reviewer_revise"},
    "draft_polisher": {"draft_polisher"},
    "setting_recorder": {"setting_recorder"},
}

VALID_NODES = sorted(NODE_EXECUTOR_NAMES.keys())


def resolve_targets(node_names: List[str], sub: str) -> Set[str]:
    """把 --node / --sub 解析为需要真实调用的 executor_name 集合。"""
    targets: Set[str] = set()
    for node in (node_names or []):
        names = NODE_EXECUTOR_NAMES.get(node)
        if not names:
            raise SystemExit(f"不支持的节点: {node}，可选: {', '.join(VALID_NODES)}")
        has_sub = any(n.endswith(("_score", "_revise")) for n in names)
        if has_sub and sub != "both":
            if sub == "review":
                names = {n for n in names if n.endswith("_score")}
            elif sub == "revise":
                names = {n for n in names if n.endswith("_revise")}
            else:
                raise SystemExit(f"不支持的 --sub: {sub}，可选 review/revise/both")
        targets |= names
    return targets


# ---------------------------------------------------------------------------
# 副作用守卫（默认不写生产表）
# ---------------------------------------------------------------------------

class SideEffectGuard:
    """将 executor 模块内绑定的写库函数替换为 no-op；--commit 时不生效。"""

    # (模块名, 函数名, 替换返回值)
    PATCH_TARGETS = [
        ("webnovel.pipeline.executors.chapter_plot_generator_executor", "add_chapter_plot", None),
        ("webnovel.pipeline.executors.chapter_plot_reviewer_executor", "add_chapter_plot", None),
        ("webnovel.pipeline.executors.setting_recorder_executor", "add_worldview", {}),
        ("webnovel.pipeline.executors.character_state_recorder_executor", "upsert_character_state", None),
    ]

    def __init__(self, commit: bool = False):
        self.commit = commit
        self._restore: List[tuple] = []

    def apply(self) -> None:
        if self.commit:
            return
        for module_name, fn_name, retval in self.PATCH_TARGETS:
            try:
                mod = importlib.import_module(module_name)
                if hasattr(mod, fn_name):
                    orig = getattr(mod, fn_name)
                    setattr(mod, fn_name, lambda *a, _r=retval, **k: _r)
                    self._restore.append((mod, fn_name, orig))
            except Exception:
                pass

    def restore(self) -> None:
        for mod, fn_name, orig in self._restore:
            try:
                setattr(mod, fn_name, orig)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 运行器
# ---------------------------------------------------------------------------

class PromptDiagRunner:
    """提示词诊断运行器。"""

    def __init__(self, args):
        self.args = args

    async def run(self) -> Dict[str, Any]:
        script_id = int(self.args.script)
        chapter_index = int(self.args.chapter)

        from webnovel.repositories import get_webnovel_project_by_script
        project = get_webnovel_project_by_script(script_id)
        if not project:
            raise SystemExit(f"未找到 script_id={script_id} 对应的项目")
        project_id = int(project["id"])

        # ---- 快照与策略 ---------------------------------------------------
        snap = SnapshotStore(script_id, chapter_index, self.args.snapshot_dir)
        need_snapshot = bool(self.args.fresh) or not snap.exists()
        if need_snapshot:
            if not self.args.fresh:
                raise SystemExit(
                    f"快照不存在：{snap.base}\n"
                    "首次使用请先运行 --fresh 生成基准快照"
                    "（一次性全量真实调用；之后默认模式仅保留上下文分析调用）。"
                )
            policy = CallPolicy(real_all=True, no_rag=self.args.no_rag, snapshot=snap)
        else:
            snap.load()
            targets = resolve_targets(self.args.node, self.args.sub)
            policy = CallPolicy(
                real_all=False,
                only_context=self.args.only_context,
                targets=targets,
                no_rag=self.args.no_rag,
                snapshot=snap,
            )
            if snap.fingerprint_changed(project_id):
                print(
                    f"[warn] DB 数据指纹与快照不一致（{snap.manifest.get('db_fingerprint')} "
                    f"→ {snap.db_fingerprint(project_id)}），如数据有变更请 --fresh 重建快照"
                )

        if self.args.with_create:
            policy.real_all = True

        # ---- 运行记录 -----------------------------------------------------
        recorder = RunRecorder(script_id, chapter_index, self.args.runs_dir, self.args.tag)

        # ---- 副作用守卫 + 模型入口注入 ------------------------------------
        guard = SideEffectGuard(commit=self.args.commit)
        guard.apply()

        import core.model_executor as me
        orig_get = me.get_model_executor
        diag = DiagnosticModelExecutor(policy, recorder)
        me.get_model_executor = lambda: diag
        # 覆盖 executor 模块顶层 `from core.model_executor import get_model_executor`
        # 的绑定（顶层 import 在模块加载时固化，仅替换 core.model_executor 属性不够）。
        import webnovel.pipeline.executors  # noqa: F401  确保所有 executor 模块已加载
        for _mod_name, _mod in list(sys.modules.items()):
            if _mod_name.startswith("webnovel.pipeline.executors.") and hasattr(_mod, "get_model_executor"):
                setattr(_mod, "get_model_executor", lambda: diag)

        steps: List[str] = []
        meta: Dict[str, Any] = {}
        try:
            from webnovel.pipeline.orchestrator import PipelineOrchestrator
            steps = list(PipelineOrchestrator.WORKFLOW_MODELS.get(
                self.args.mode, PipelineOrchestrator.DEFAULT_STEPS))
            context: Dict[str, Any] = {
                "script_id": script_id,
                "chapter_index": chapter_index,
                "task_id": 0,
                "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "step_results": {},
                "step_selections": {},
            }
            if self.args.user_prompt:
                context["user_prompt"] = self.args.user_prompt

            for step_name in steps:
                cls = PipelineOrchestrator.EXECUTOR_REGISTRY.get(step_name)
                if cls is None:
                    print(f"[skip] 未注册的步骤: {step_name}")
                    continue
                print(f"[run ] {step_name} ...")
                executor = cls(script_id, chapter_index, 0)
                try:
                    result = await executor.execute(context)
                except Exception as exc:
                    print(f"[fail] {step_name}: {type(exc).__name__}: {exc}")
                    recorder.record_step_error(step_name, exc)
                    continue
                recorder.record_step(step_name, result)
                if getattr(result, "success", False):
                    output = getattr(result, "output_data", None) or {}
                    context["step_results"][step_name] = output
                    context.update(output)
                    print(f"[ok  ] {step_name}: {getattr(result, 'step_summary', '') or ''}")
                else:
                    print(f"[fail] {step_name}: {getattr(result, 'error_message', '') or '未知错误'}")

            # 快照保存
            if need_snapshot:
                meta = {
                    "script_id": script_id,
                    "chapter_index": chapter_index,
                    "mode": self.args.mode,
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "db_fingerprint": snap.db_fingerprint(project_id),
                    "policy": "fresh_full_real",
                }
                snap.save(meta, recorder.calls, context.get("step_results", {}))
                print(f"[snap] 快照已保存: {snap.base}")
        finally:
            me.get_model_executor = orig_get
            guard.restore()

        # ---- 汇总与报告 ---------------------------------------------------
        diffs = recorder.write_diffs(self.args.tag)
        extra = {
            "script_id": script_id,
            "chapter_index": chapter_index,
            "mode": self.args.mode,
            "nodes": list(resolve_targets(self.args.node, self.args.sub)) if self.args.node else [],
            "only_context": self.args.only_context and not self.args.with_create,
            "with_create": bool(self.args.with_create),
            "fresh": bool(self.args.fresh),
            "snapshot": snap.base,
            "run_dir": recorder.dir,
            "diff_files": diffs,
        }
        summary = recorder.finalize(extra)

        from tools.prompt_diag.report import build_report
        try:
            report_path = build_report(recorder, summary)
        except Exception as exc:
            report_path = None
            print(f"[warn] 报告生成失败: {exc}")

        if self.args.model:
            print(
                "[info] --model 为预留参数：当前版本请通过 config 的调用点模型覆盖"
                "（get_call_point_model / call_point_override）配置，本参数暂不生效。"
            )

        print("\n==== 运行汇总 ====")
        print(f"  运行目录: {recorder.dir}")
        print(f"  LLM 调用: {summary['llm_calls']}（real={summary['by_decision']['real']}, "
              f"replay={summary['by_decision']['replay']}, skip={summary['by_decision']['skip']}）")
        print(f"  tokens  : in={summary['tokens_in']} out={summary['tokens_out']}")
        print(f"  耗时    : {summary['elapsed_s']}s，步骤失败 {summary['step_failures']} 个")
        if report_path:
            print(f"  报告    : {report_path}")
        return summary
