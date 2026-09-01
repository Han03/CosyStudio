# CosyStudio

> 一站式本地 AI 网文创作与有声书生成平台 —— 从大纲构建到章节写作、从语音合成到整章配音，全流程本地化运行。

![version](https://img.shields.io/badge/version-1.0-blue)
![python](https://img.shields.io/badge/python-3.10%2B-green)
![license](https://img.shields.io/badge/license-MIT-orange)

---

## 核心功能

### 网文写作流水线

完整的 AI 辅助网文创作系统，覆盖从项目初始化到章节成稿的全流程。采用多执行器流水线架构，每个执行器负责一个独立步骤，通过编排器统一调度，支持中断恢复和 WebSocket 实时进度推送。

#### 写作流水线（核心创作路径）

```
上下文构建 → 剧情生成 → 剧情审查 → 草稿生成 → 草稿审查 → 草稿润色 → 事实记录 → 伏笔/爽点提取
```

| 步骤 | 执行器 | 说明 |
|------|--------|------|
| 上下文构建 | ContextBuilder | 组装核心设定、角色卡片、金手指、力量体系、世界观、卷章规划、前文回顾、RAG 语义检索结果、反套路规则 |
| 剧情生成 | ChapterPlotGenerator | 基于章节规划和上下文，生成场景级详细剧情列表 |
| 剧情审查 | ChapterPlotReviewer | 多维度质量审查（规划覆盖/因果逻辑/冲突张力），低于 7 分自动触发修正，最多 2 轮 |
| 草稿生成 | DraftGenerator | 基于剧情列表创作 2000-3000 字正文草稿 |
| 草稿审查 | DraftReviewer | 5 维度审查（爽点呈现/设定一致/节奏控制/叙事连贯/追读力），最多 3 次修改迭代 |
| 草稿润色 | DraftPolisher | 将审查后的草稿润色为最终小说文本 |
| 事实记录 | FactRecorder | 从成稿中提取关键事实（新角色/关系变化/重要事件/伏笔/世界观补充） |
| 伏笔/爽点提取 | ForeshadowCoolPointExtractor | 提取伏笔（核心/支线/装饰三级）和爽点（15 种类型：装逼打脸/越级反杀/逆袭等） |

#### 项目初始化（7 步引导式创建）

分步交互式创建项目，每步均支持 AI 辅助生成：

1. **基础信息** — 书名、题材、目标字数
2. **主角设定** — 性格、背景、说话风格
3. **金手指设定** — 类型、风格、代价
4. **世界观设定** — 地理、社会、资源、信仰
5. **创意约束包** — AI 生成 3 个反套路规则方案供选择
6. **确认执行** — 将所有设定写入数据库

#### 卷纲规划

完整的卷纲规划流程：补齐设定基线 → 选择目标卷 → 生成节拍表 → 生成时间线 → 生成骨架 → 批量生成章纲 → 验证保存。

#### 质量保障

- **剧情审查**：规划覆盖率、因果逻辑、冲突张力，2 轮自动修正
- **草稿审查**：爽点呈现、设定一致性、节奏控制、叙事连贯、追读力，3 轮迭代修改
- **独立审查**：8 维度全面质量审查（爽点/打脸/设定/节奏/OOC/连贯/追读/对话/描写）
- **RAG 语义检索**：基于 Qwen3-Embedding 的向量存储，写作时自动检索相关前文，保持上下文连贯
- **伏笔追踪**：自动提取并管理伏笔（open_loops），支持 urgency 状态更新
- **爽点追踪**：15 种爽点类型自动识别与记录

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
| **剧本编辑器** | 网文创作核心工作台，集成初始化/卷纲/创作/审查全流程 |
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
│   ├── core/                    #   核心模块（模型调度、配置、路径）
│   ├── models/                  #   模型封装
│   │   ├── cosyvoice/           #     CosyVoice3 TTS 引擎
│   │   ├── cosyvoice_model.py   #     TTS 模型接口
│   │   ├── dreamlite_model.py   #     文生图模型接口
│   │   ├── qwen_model.py        #     LLM 模型接口
│   │   └── qwen_embedding_model.py  # Embedding 模型接口
│   ├── repositories/            #   数据访问层（SQLite）
│   ├── services/                #   业务逻辑层
│   ├── webnovel/                #   网文创作模块
│   │   ├── api/                 #     创作流程 API 路由
│   │   ├── pipeline/            #     写作流水线执行器
│   │   │   └── executors/       #       各步骤执行器
│   │   ├── repositories/        #     网文专用数据访问层
│   │   ├── prompts/             #     LLM Prompt 模板
│   │   └── services/            #     网文业务服务
│   ├── utils/                   #   工具类
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
└── data/                        # 运行时数据（缓存/日志/输出）
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
│  进度广播 (WebSocket) │ 中断恢复 │ 多工作流模式         │
└─────────────────────────┬────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────┐
│            Core 层 (模型统一调度)                       │
│  ModelExecutor ← ConfigManager ← ModelManager         │
│  QwenModel │ CosyVoiceModel │ DreamLiteModel          │
│  QwenEmbeddingModel                                   │
└─────────────────────────┬────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────┐
│             Repository 层 (数据持久化)                  │
│  app.db │ vector_store.db │ llm_logs.db          │
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
conda create -n cosy_studio python=3.10
conda activate cosy_studio

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

# 方式二：启动 Web 服务 + Kivy 桌面 GUI
cd backend
python start_server.py
```

服务默认运行在 `http://localhost:8080`，可在 `config/system_config.json` 的 `system.port` 修改端口。

### 使用流程

1. 打开浏览器访问 `http://localhost:8080/script_editor.html` 进入剧本编辑器
2. 创建新项目，按 7 步引导完成初始化（每步可 AI 辅助生成）
3. 进行卷纲规划，生成章节大纲
4. 选择写作模式，开始 AI 创作，实时查看进度
5. 创作完成后，使用整章配音功能生成有声书

---

## 主要 API

### 网文创作

| 端点 | 说明 |
|------|------|
| `POST /webnovel/init` | 深度初始化项目 |
| `POST /webnovel/plan` | 卷纲规划 |
| `POST /webnovel/write` | 章节写作（支持 write/write_fast/write_minimal） |
| `POST /webnovel/review` | 质量审查 |
| `POST /chapters/continue` | 创作章节（核心入口） |
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
