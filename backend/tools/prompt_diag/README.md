# 智能创作提示词诊断脚本（tools.prompt_diag）

针对写小说（智能创作）流水线（script_id=999912 等）的 **prompt 诊断专用工具**：
指定某一节点做真实 LLM 调用，其余节点用基准快照回放；默认只保留**上下文分析**
（context_analyzer）的真实调用，实现低成本、可对照、可留档的单点 prompt 调优。

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 指定节点诊断 | `--node chapter_plot_reviewer` 等，只对该节点真实调用 |
| 跳过创作 LLM 调用 | 默认情节生成/评审/修订/草稿等创作节点全部快照回放，零 token |
| 默认仅保留上下文分析 | 默认模式下只有 `context_analyzer` 真实调用 |
| 多轮可对照 | 同一快照反复运行，`--tag` 分组并生成 prompt/输出 diff |
| 隔离生产数据 | 默认将写库函数替换为 no-op，`--commit` 才放行 |

## 运行前提

- 在 `backend` 目录下执行：`python -m tools.prompt_diag ...`
- 需要模型能力可用（真实调用会走 config 中配置的云端/本地模型）。
- **首次使用先 `--fresh` 生成基准快照**（一次性全量真实调用，之后可反复低成本使用）。

## 用法

```bash
# 1) 首次生成基准快照（一次性全量真实调用，约等于一次完整写作的成本）
python -m tools.prompt_diag --script 999912 --chapter 8 --fresh

# 2) 默认模式：仅 context_analyzer 真实调用，其余节点快照回放
python -m tools.prompt_diag --script 999912 --chapter 8

# 3) 单节点诊断：只真调"评审打分"，剧情输入固定为快照
python -m tools.prompt_diag --script 999912 --chapter 8 \
    --node chapter_plot_reviewer --sub review --tag exp1

# 4) 修订节点单独诊断（固定 plot + issues 输入）
python -m tools.prompt_diag --script 999912 --chapter 8 \
    --node chapter_plot_reviewer --sub revise --tag exp1

# 5) 只调上下文选择逻辑（跳过向量检索）
python -m tools.prompt_diag --script 999912 --chapter 8 --no-rag

# 6) 全量真实（对照现网）
python -m tools.prompt_diag --script 999912 --chapter 8 --with-create
```

## 参数

| 参数 | 说明 |
| --- | --- |
| `--script` / `--chapter` | 剧本与章节（必填） |
| `--node` | 指定诊断节点，可重复：`context_analyzer`、`chapter_plot_generator`、`chapter_plot_reviewer`、`chapter_plot_reviewer_revise`、`draft_generator`、`draft_reviewer`、`draft_polisher`、`setting_recorder` |
| `--sub review\|revise\|both` | 评审类节点的子调用细分（默认 both） |
| `--mode` | `write` / `write_fast` / `write_minimal`（默认 write） |
| `--only-context` | 默认行为：仅 context_analyzer 真实调用 |
| `--with-create` | 全量真实调用（与 `--only-context` 互斥） |
| `--fresh` | 重新生成基准快照（全量真实） |
| `--no-rag` | 跳过向量检索（RAG 结果为空） |
| `--tag` | 实验标签，用于同标签前后运行 diff |
| `--commit` | 允许写生产表（默认不写） |
| `--snapshot-dir` / `--runs-dir` | 自定义快照 / 运行结果目录 |

## 产物

```
data/diag_snapshots/<script>/<chapter>/   # 基准快照
  manifest.json   元信息 + DB 指纹
  calls.jsonl     基准运行的完整 LLM 调用（供 REPLAY）
  steps.json      各步骤输出

data/diag_runs/<script>/<chapter>/<tag>_<ts>/   # 每次运行结果
  calls.jsonl     每次调用的 prompt/raw/tokens/延迟/决策
  summary.json    统计
  diff/           与上一次同 tag 运行的对比
  report.html     可视化报告
```

## 实现机制

- **注入点**：所有 executor 通过 `core.model_executor.get_model_executor()` 取单例；
  诊断脚本替换该函数返回值，在统一入口拦截（`policy.py`）。
- **决策**：`context_analyzer`（默认）与 `--node` 目标 → REAL；其余创作节点 → REPLAY（返回快照输出）。
- **日志**：真实调用照常写 `llm_call_logs`；回放调用写 `success_strategy=diag_replay`，
  并通过 log bridge 让 `parse_llm_json` 回写同一条记录。
- **副作用**：`runner.py` 默认替换 `add_chapter_plot` / `add_worldview` 为 no-op，不写生产表。

## 限制

- 快照基于生成时的 DB 状态；角色卡/伏笔/章节规划变更后需 `--fresh` 重建（manifest 记录 DB 指纹并提示）。
- `--model` 为预留参数，当前版本请通过 config 的调用点模型覆盖配置生效。
- 本地模型需已配置/可加载；诊断脚本按串行方式执行。
