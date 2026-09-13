# CosyStudio

> 一站式本地 AI 网文创作与有声书生成平台 —— 从大纲构建到章节写作、从语音合成到整章配音，全流程本地化运行。

![version](https://img.shields.io/badge/version-1.1-blue)
![python](https://img.shields.io/badge/python-3.10%2B-green)
![license](https://img.shields.io/badge/license-MIT-orange)

---

## 核心功能

### 网文写作流水线

完整的 AI 辅助网文创作系统，覆盖从项目初始化到章节成稿的全流程。采用多执行器流水线架构，每个执行器负责一个独立步骤，通过编排器统一调度，支持中断恢复和 WebSocket 实时进度推送。

#### 上下文分析（ContextAnalyzer）

在每一个创作/审查节点调用 LLM 生成前，先由轻量级 LLM 分析确定该步骤**需要哪些上下文条目**（角色/前文/伏笔/世界观/力量体系/金手指/RAG 查询/一致性要点），再从数据库精准加载完整数据、执行 RAG 语义检索，组装最终上下文供执行器使用——替代原有"全量加载 + 硬编码裁剪"策略，降低 token 成本并保证各节点只看到必要的设定。

每个节点有独立的**字段白名单**与**一致性维度清单**（如草稿生成：角色行为与性格一致、角色状态连续、物品清单约束、前文自然承接、信息暴露边界、能力行为边界），由分析器生成 `consistency_notes` 注入创作节点。

#### 写作流水线（核心创作路径）

```
上下文构建 → 剧情生成 → 剧情审查 → 草稿生成 → 草稿审查 → 草稿润色 → 应用结果
（每个节点前：ContextAnalyzer 按需组装上下文）
```

| 步骤 | 执行器 | 说明 |
|------|--------|------|
| 上下文构建 | ContextBuilder | 组装核心设定、角色卡片、金手指、力量体系、世界观、卷章规划、前文回顾、RAG 语义检索结果、反套路规则，生成上下文清单供 ContextAnalyzer 选择 |
| 剧情生成 | ChapterPlotGenerator | 基于章节规划和上下文，生成场景级详细剧情列表 |
| 剧情审查 | ChapterPlotReviewer | 多维度质量审查（规划覆盖/因果逻辑/冲突张力），低于 7 分自动触发修正，最多 2 轮 |
| 草稿生成 | DraftGenerator | 基于剧情列表创作白描草稿（默认约成品字数的 40%） |
| 草稿审查 | DraftReviewer | 5 维度审查（爽点呈现/设定一致/节奏控制/叙事连贯/追读力），最多 3 次修改迭代 |
| 草稿润色 | DraftPolisher | 将审查后的草稿润色为最终小说文本（默认成品区间，见字数参数化） |
| 角色状态记录 | CharacterStateRecorder | 按章记录各角色位置/状态/情绪/已知信息，供下一章创作注入（"角色状态连续"约束） |

**写作模式**（`POST /webnovel/write` 的 `mode` 参数）：

| 模式 | 步骤 | 适用 |
|------|------|------|
| `write` | 完整链路 + 角色状态记录/设定记录 | 标准创作 |
| `write_fast` | 完整链路（不含状态/设定记录） | 快速出稿 |
| `write_minimal` | 剧情→草稿→润色（无审查迭代） | 最低成本草稿 |

**字数参数化**：`WriteRequest.chapter_words` 可指定单章成品目标字数（默认 4000）。系统自动推导各节点区间（润色 ±20%、白描 ×0.4）并联动 `max_tokens`，后续可在配置中调整。

#### 项目初始化（7 步引导式创建）

分步交互式创建项目，每步均支持 AI 辅助生成：

1. **基础信息** — 书名、题材、目标字数
2. **主角设定** — 性格、背景、说话风格
3. **金手指设定** — 类型、风格、代价
4. **世界观设定** — 地理、社会、资源、信仰
5. **创意约束包** — AI 生成 3 个反套路规则方案供选择
6. **确认执行** — 将所有设定写入数据库

另有**深度初始化**（`/webnovel/init`）批量构建角色卡（含身份/性格/能力/OOC 警告等字段）与项目基线数据。

#### 卷纲规划

完整的卷纲规划流程：补齐设定基线 → 选择目标卷 → 生成节拍表 → 生成时间线 → 生成骨架 → 批量生成章纲 → 验证保存。

#### 应用结果（创作完成后的后处理）

创作内容保存为章节后，自动执行（`apply-task`，可单独重跑 `retry-post-process`）：

| 步骤 | 说明 |
|------|------|
| 章节保存 | 内容过滤、标题提取、写入章节文件 |
| 事实记录（FactRecorder） | **一次 LLM 调用结构化提取六块**：物品变化（获得/失去扣减，追加流水）、角色更新（关系/身份揭露/成长/能力）、伏笔（核心/支线/装饰三级）、爽点（15 种类型）、结尾钩子、角色状态 |
| 新角色建卡 | 正文出现的新角色自动建角色卡并写入关系 |
| 伏笔回收检查 | 对照已埋伏笔自动判定回收/更新 urgency |
| 角色卡 RAG 增量重建 | 物品/身份/改名涉及的角色卡增量重建向量索引 |
| RAG 索引构建 | 新章节内容入向量库，供后续章节语义检索 |

Phase 1 的 LLM 调用在云端模式下并发执行，本地模式自动串行。

#### 质量保障

- **剧情审查**：规划覆盖率、因果逻辑、冲突张力，2 轮自动修正
- **草稿审查**：爽点呈现、设定一致性、节奏控制、叙事连贯、追读力，3 轮迭代修改
- **一致性约束**：ContextAnalyzer 按节点生成 `consistency_notes`（角色状态连续/物品清单约束/知识边界/时间线等），注入每个创作节点
- **角色状态连续**：上一章角色状态自动注入本章创作，防止角色"失忆"/状态漂移
- **RAG 语义检索**：基于 Qwen3-Embedding 的向量存储，写作时自动检索相关前文，保持上下文连贯
- **伏笔追踪**：自动提取并管理伏笔（open_loops），支持 urgency 状态更新与回收判定
- **爽点追踪**：15 种爽点类型自动识别与记录

#### 诊断与可观测性

| 能力 | 说明 |
|------|------|
| **prompt_diag**（`backend/tools/prompt_diag`） | 创作提示词诊断专用脚本：指定流水线某一节点真实调用，其余节点用基准快照回放；默认只保留上下文分析真实调用，实现低成本、可对照的单点 prompt 调优（`--node` / `--tag` / `--no-rag` / `--commit` 等） |
| **pipeline_diag**（`backend/tools/pipeline_diag`） | 全流程诊断工具：每次运行把每一步执行过程（每次 LLM 调用的完整 prompt/输出、每个执行器步骤耗时、每次 DB 写入 SQL 与参数）记录到独立文件夹，供离线分析可优化节点 |
| **LLM 调用日志** | 所有 LLM 调用经统一入口（`execute_text_chat`）写入 `app_llm_logs.db`（`llm_call_logs` 表），含 script/project/executor/prompt_name/system_prompt/user_prompt/raw_output/解析结果/tokens/延迟/报错；解析结果经桥接回写同一条记录，出错也能追溯 |

#### 辅助工具

| 工具 | 说明 |
|------|------|
| 状态查询 | 根据自然语言查询项目设定信息 |
| 项目学习 | 从成功案例中提取可复用的写作模式 |

### 有声书生成

基于 CosyVoice3 的语音合成系统，支持从单句配音到整章有声书生成的完整链路。

#### 整章配音

```
章节台词列表 → 逐句语音合成 → 音频拼接 → 完整 WAV + SRT 字幕 → 打包下载
```

- **整章合成**：自动遍历章节所有台词，逐句合成后拼接为完整音频文件，同时生成 SRT 字幕文稿
- **整章导出**：合成并打包为 ZIP（audio.wav + subtitles.srt）直接下载
- **配音历史**：保存每次合成的完整记录，支持回听和重新下载

#### 单句配音

- **流式合成**：NDJSON 流式输出 PCM 音频，边合成边播放
- **台词配音**：根据台词 ID 自动获取文本、角色、语气参数，一键合成
- **参数控制**：支持音量调节、变调、淡入淡出、区间裁剪

#### 音频缓存

相同文本 + 角色 + 语气的合成结果自动缓存，重复台词无需重新合成，大幅提升整章配音效率。

---

## 其他功能

| 模块 | 说明 |
|------|------|
| **智能对话** | 基于 Qwen 的流式文本对话，支持多轮上下文 |
| **AI 智能体** | 创建个性化智能体，自定义人设、音色与行为参数 |
| **语音通话** | 语音输入 → ASR 转写 → LLM 回复 → TTS 语音输出全链路 |
| **文生图** | 基于 DreamLite 的本地图像生成 |
| **语音识别** | 基于 Whisper 的语音转文字，支持繁简转换 |
| **电子书管理** | TXT/EPUB 上传、自动章节拆分、在线阅读 |
| **剧本编辑器** | 网文创作核心工作台，集成初始化/卷纲/创作/审查全流程，实时进度推送 |
| **模型管理** | 统一管理本地模型与云端 API，按需加载/卸载 |
| **系统监控** | 实时 CPU/内存/磁盘/GPU 资源监控，WebSocket 日志推送 |

### 支持的 AI 平台

| 平台 | 能力 |
|------|------|
| 本地模型 | 文本 / TTS / 文生图 / Embedding |
| 阿里云 (DashScope) | 文本 / TTS / 文生图 |
| 智谱 AI | 文本 |
| 火山引擎 (豆包) | 文本 |
| OpenRouter | 文本 |
| DeepSeek / Google Gemini / 百度文心 | 文本（可选） |

---

## 技术栈

| 层 | 技术 |
|----|------|
| **后端框架** | FastAPI + Uvicorn，SQLite (WAL) 数据持久化 |
| **AI 推理** | PyTorch 2.10 + CUDA，Transformers 5.13，CosyVoice3，DreamLite，Qwen3.5 |
| **语音合成** | CosyVoice3-0.5B，支持多音色、流式输出 |
| **语音识别** | OpenAI Whisper |
| **图像生成** | DreamLite-mobile-4bit，基于 Diffusers |
| **文本嵌入** | Qwen3-Embedding-0.6B，用于 RAG 语义检索 |
| **前端** | 原生 HTML/JS，Bootstrap 5，WebSocket 实时通信 |
| **桌面 GUI** | Kivy 2.3（可选，服务端日志界面） |

---

## 项目结构

```
CosyStudio/
├── backend/                     # 后端服务
│   ├── api/                     #   REST API 路由
│   ├── agents/                  #   智能体管理
│   ├── core/                    #   核心模块（模型调度、配置、路径、LLM 调用上下文）
│   ├── models/                  #   模型封装
│   │   ├── cosyvoice/           #     CosyVoice3 TTS 引擎
│   │   ├── cosyvoice_model.py   #     TTS 模型接口
│   │   ├── dreamlite_model.py   #     文生图模型接口
│   │   ├── qwen_model.py        #     LLM 模型接口
│   │   └── qwen_embedding_model.py  # Embedding 模型接口
│   ├── repositories/            #   数据访问层（SQLite）
│   ├── services/                #   业务逻辑层
│   ├── tools/                   #   诊断工具
│   │   ├── prompt_diag/         #     创作提示词诊断（快照回放/单点调优）
│   │   └── pipeline_diag/       #     全流程诊断（步骤/LLM/DB 写入留档）
│   ├── webnovel/                #   网文创作模块
│   │   ├── api/                 #     创作流程 API 路由
│   │   ├── pipeline/            #     写作流水线
│   │   │   ├── orchestrator.py  #       流水线编排器（工作流模式/字数参数化）
│   │   │   ├── context_analyzer.py   #   LLM 按需上下文组装（字段白名单/一致性约束）
│   │   │   └── executors/       #       各步骤执行器（含角色状态记录器）
│   │   ├── repositories/        #     网文专用数据访问层（角色状态/角色卡/伏笔等）
│   │   ├── prompts/             #     LLM Prompt 模板（含 context_analysis_prompt）
│   │   └── services/            #     网文业务服务（创作/应用结果/后处理）
│   ├── utils/                   #   工具类（LLM JSON 解析/统一日志）
│   └── widgets/                 #   Kivy GUI 组件
├── frontend/                    # 前端静态资源
│   ├── index.html               #   主页（对话/模型管理/监控）
│   ├── script_editor.html       #   剧本编辑器（创作工作台）
│   ├── ebook_reader.html        #   电子书阅读器
│   └── assets/                  #   CSS / JS / 字体
├── config/                      # 系统配置
├── pretrained_models/           # 本地预训练模型
├── media/                       # 媒体资源
├── bin/                         # 第三方二进制工具（ffmpeg/xray）
└── data/                        # 运行时数据（缓存/日志/输出/诊断产物）
```

---

## 架构设计

```
┌──────────────────────────────────────────────────────┐
│                    前端 (HTML/JS)                      │
│   index.html  │  script_editor.html  │  ebook_reader  │
└─────────────────────────┬────────────────────────────┘
                          │ HTTP / WebSocket
┌─────────────────────────▼────────────────────────────┐
│                  API 层 (FastAPI)                      │
│  webnovel/api │ audio │ books │ agents │ text_chat ... │
└─────────────────────────┬────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────┐
│               Service 层 (业务逻辑)                    │
│  webnovel_service │ audio_service │ script_service     │
│  chat │ ebook_library │ media_manager │ vector_store   │
└─────────────────────────┬────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────┐
│         Pipeline 层 (写作流水线编排)                    │
│  PipelineOrchestrator → [Executor1 → Executor2 → ...] │
│  ContextAnalyzer（按需组装上下文） │ RAG 检索           │
│  进度广播 (WebSocket) │ 中断恢复 │ 多工作流模式         │
└─────────────────────────┬────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────┐
│            Core 层 (模型统一调度)                       │
│  ModelExecutor ← ConfigManager ← ModelManager         │
│  QwenModel │ CosyVoiceModel │ DreamLiteModel          │
│  QwenEmbeddingModel │ LLM 调用统一日志入口             │
└─────────────────────────┬────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────┐
│             Repository 层 (数据持久化)                  │
│  app.db │ vector_store.db │ app_llm_logs.db      │
└──────────────────────────────────────────────────────┘
```

---

## 快速开始

### 环境要求

- Python >= 3.10
- NVIDIA GPU + CUDA（本地模型推理需要）
- conda 环境（推荐）

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd CosyStudio

# 创建 conda 环境
conda create -n cosy_chat python=3.10
conda activate cosy_chat

# 安装依赖
pip install -r backend/requirements.txt
```

### 配置模型

编辑 `config/system_config.json`，设置本地模型路径：

```json
{
  "models": {
    "cosyvoice": {
      "model_path": "pretrained_models/cosyvoice/CosyVoice3-0.5B-2512"
    },
    "qwen": {
      "model_path": "pretrained_models/qwen/Qwen_Qwen3.5-4B"
    },
    "dreamlite": {
      "model_path": "pretrained_models/dreamlite/DreamLite-mobile-4bit"
    },
    "qwen_embedding": {
      "model_path": "pretrained_models/qwen_embedding/Qwen_Qwen3-Embedding-0.6B"
    }
  }
}
```

如需使用云端 API，在同一配置文件中填写对应平台的 `api_key`。

### 启动服务

```bash
# 方式一：仅启动 Web 服务
cd backend
python main.py

# 方式二：Uvicorn 直接启动（推荐，conda 环境）
cd backend
python -m uvicorn main:app --port 8080
```

服务默认运行在 `http://localhost:8080`，可在 `config/system_config.json` 的 `system.port` 修改端口。

### 使用流程

1. 打开浏览器访问 `http://localhost:8080/script_editor.html` 进入剧本编辑器
2. 创建新项目，按 7 步引导完成初始化（每步可 AI 辅助生成）
3. 进行卷纲规划，生成章节大纲
4. 选择写作模式，开始 AI 创作，实时查看进度
5. 创作完成后自动应用结果（事实记录/伏笔/爽点/RAG 索引），使用整章配音功能生成有声书

---

## 主要 API

### 网文创作

| 端点 | 说明 |
|------|------|
| `POST /webnovel/init` | 深度初始化项目（构建角色卡/基线数据） |
| `POST /webnovel/plan` | 卷纲规划 |
| `POST /webnovel/write` | 章节写作（支持 `mode`：write/write_fast/write_minimal；`chapter_words`：单章目标字数） |
| `POST /webnovel/review` | 质量审查 |
| `POST /api/books/scripts/chapters/continue` | 创作章节（核心入口，支持 `enable_polish` / `auto_apply`） |
| `GET /api/books/scripts/chapters/continue/status` | 创作任务状态 |
| `POST /api/books/scripts/chapters/continue/cancel` | 取消创作任务 |
| `POST /api/books/scripts/chapters/continue/apply-task` | 应用创作结果（保存章节 + 后处理） |
| `POST /api/books/scripts/chapters/continue/retry-post-process` | 重跑后处理（事实记录/伏笔/爽点/钩子/RAG） |
| `GET /webnovel/dashboard` | 项目面板数据 |

### 有声书

| 端点 | 说明 |
|------|------|
| `POST /api/audio/synthesize` | 单句流式语音合成 |
| `POST /api/audio/synthesize-chapter` | 整章配音合成 |
| `POST /api/audio/export-chapter` | 整章导出 ZIP（WAV + SRT） |
| `GET /api/audio/chapter-history` | 配音历史列表 |

### 其他

| 端点 | 说明 |
|------|------|
| `POST /api/chat/stream` | 流式文本对话 |
| `POST /api/image/generate` | 文生图 |
| `POST /api/asr/transcribe` | 语音识别 |
| `POST /api/books/library/upload` | 电子书上传入库 |
| `GET/POST /api/agents` | 智能体管理 |
| `WS /ws` | WebSocket 实时日志推送 |

---

## 许可证

MIT License
