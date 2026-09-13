# 全流程诊断工具（pipeline_diag）

用于分析「智能创作 + 应用结果」全流程中可优化的节点。每次运行把**每一步的详细执行过程**记录到
一个独立文件夹，后续可离线分析提示词质量、输入输出、入库内容与耗时。

## 记录内容

每次运行生成 `backend/data/pipeline_diag_runs/<script_id>/<chapter>/<tag>_<时间戳>/`：

| 文件 | 内容 |
| --- | --- |
| `llm_calls.jsonl` | 每次 LLM 调用：executor_name、prompt_name、**system_prompt、user_prompt、raw_output**、模型、tokens、延迟、所属步骤/阶段 |
| `steps.jsonl` | 每个执行器步骤：步骤名、耗时、成功与否、期间发生的 LLM 调用序号区间与 DB 写入序号区间 |
| `db_writes.jsonl` | 每次 DB 写（INSERT/UPDATE/DELETE/REPLACE）：**表名、SQL、参数**、所属步骤/LLM 调用 |
| `events.jsonl` | 阶段标记（writing / apply）与异常事件时间线 |
| `meta.json` | 剧本/章节/起止时间/总耗时/参数 |
| `summary.json` | 汇总：按 `executor|prompt_name` 统计 LLM 调用（次数/tokens/延迟/错误）、按表统计写入次数、步骤清单 |

## 捕获机制（不改业务代码）

- **LLM 调用**：包装 `core.model_executor.ModelExecutor.execute_text_chat`——系统所有 LLM 调用
  的统一出口（executor 与 service 内直接调用均覆盖）。
- **执行器步骤**：包装 `webnovel.pipeline.executors` 中每个继承 `BaseExecutor` 的类的
  `execute`——每个流水线节点一步。
- **DB 写**：对 `app.db` 全局连接 `set_trace_callback`——记录写语句与参数（超长参数截断）。

## 用法

```bash
cd backend
# conda cosy_chat 环境的 python 绝对路径
& "C:\app\miniconda3\envs\cosy_chat\python.exe" tools/pipeline_diag/runner.py --script 999913 --chapter 2 --tag ch2_first
```

参数：
- `--script`：剧本 script_id（如 999913）
- `--chapter`：章节目录索引（如 2 = 第二章）
- `--tag`：运行标签，用于区分多次运行
- `--no-polish`：关闭润色节点（走草稿审查直接出稿）
- `--timeout`：总超时秒数（默认 7200）
- `--dry-init`：仅初始化自检（不跑流程）

## 注意

- 真实跑创作需要本地 Qwen 模型加载（首次加载数分钟），embedding/rerank 按需加载；
  磁盘占用按运行体积定，`llm_calls.jsonl` 含完整 prompt 与输出，正文章节几万字属正常。
- 运行器与 Web 服务是两个独立进程，共享 `app.db`（WAL 模式），服务端有进行中任务时会互斥拒绝。
- 分析某节点时，先看 `summary.json` 的步骤与 LLM 统计，再按序号在 `llm_calls.jsonl` /
  `db_writes.jsonl` 中精读对应记录。
