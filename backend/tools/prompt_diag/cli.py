# -*- coding: utf-8 -*-
"""提示词诊断脚本 CLI 入口。

用法示例（在 backend 目录下运行）：
    # 首次生成基准快照（一次性全量真实调用）
    python -m tools.prompt_diag --script 999912 --chapter 8 --fresh

    # 默认模式：仅上下文分析真实调用，其余节点快照回放
    python -m tools.prompt_diag --script 999912 --chapter 8

    # 单节点诊断：只真调评审打分（输入剧情固定为快照）
    python -m tools.prompt_diag --script 999912 --chapter 8 --node chapter_plot_reviewer --sub review --tag exp1
"""

import argparse
import asyncio
import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from tools.prompt_diag.runner import VALID_NODES, PromptDiagRunner


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.prompt_diag",
        description="智能创作提示词诊断脚本：指定节点诊断 / 默认仅保留上下文分析 LLM 调用",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--script", type=int, required=True, help="剧本 script_id（如 999912）")
    p.add_argument("--chapter", type=int, required=True, help="章节号 chapter_index")
    p.add_argument(
        "--node", action="append", choices=VALID_NODES, default=None, metavar="NODE",
        help="指定诊断节点（可重复）。可选: " + ", ".join(VALID_NODES),
    )
    p.add_argument(
        "--sub", choices=["review", "revise", "both"], default="both",
        help="对含评审/修订子调用的节点（chapter_plot_reviewer / draft_reviewer）细分（默认 both）",
    )
    p.add_argument(
        "--mode", choices=["write", "write_fast", "write_minimal"], default="write",
        help="流水线形态（默认 write）",
    )
    grp = p.add_mutually_exclusive_group()
    grp.add_argument(
        "--only-context", action="store_true",
        help="默认行为：仅 context_analyzer 真实调用，创作节点全部快照回放",
    )
    grp.add_argument(
        "--with-create", action="store_true",
        help="全量真实调用（创作节点也真调），用于对照现网",
    )
    p.add_argument(
        "--fresh", action="store_true",
        help="重新生成基准快照（一次性全量真实调用）",
    )
    p.add_argument(
        "--no-rag", action="store_true",
        help="跳过向量检索调用（RAG 结果为空，适合只调上下文选择逻辑）",
    )
    p.add_argument("--model", default=None, help="预留：目标节点模型覆盖（当前版本请通过 config 调用点配置）")
    p.add_argument("--snapshot-dir", default=None, help="快照目录（默认 data/diag_snapshots/<script>/<chapter>）")
    p.add_argument("--runs-dir", default=None, help="运行结果目录（默认 data/diag_runs/<script>/<chapter>）")
    p.add_argument("--tag", default=None, help="实验标签：用于与上一次同 tag 运行生成 diff")
    p.add_argument("--commit", action="store_true", help="允许写生产表（默认不写）")
    p.add_argument("--user-prompt", default=None, help="用户创作指令（透传给 context['user_prompt']）")
    return p


def main() -> None:
    args = build_parser().parse_args()
    try:
        summary = asyncio.run(PromptDiagRunner(args).run())
    except KeyboardInterrupt:
        print("\n[abort] 已中断")
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[error] {type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
