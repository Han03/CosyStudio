# CosyChat

> 一站式本地 AI 创作与对话平台 —— 集成文本对话、语音合成、文生图、网文创作、电子书管理等能力，所有模型均可本地部署运行。

![version](https://img.shields.io/badge/version-4.34.3-blue)
![python](https://img.shields.io/badge/python-3.13%2B-green)
![license](https://img.shields.io/badge/license-MIT-orange)

---

## 功能概览

| 模块 | 说明 |
|------|------|
| **智能对话** | 基于 Qwen 等大模型的流式文本对话，支持多轮上下文 |
| **AI 智能体** | 创建、编辑、管理个性化智能体，自定义人设与行为 |
| **语音合成 (TTS)** | 基于 CosyVoice3 的本地语音合成，支持多种音色 |
| **文生图** | 基于 DreamLite 的本地图像生成，支持自定义分辨率与步数 |
| **语音识别 (ASR)** | 基于 Whisper 的语音转文字，支持繁简转换 |
| **网文创作** | 完整的网文创作流水线：深度初始化 → 卷章规划 → AI 写作 → 审查润色 |
| **电子书管理** | 上传/解析电子书，自动章节拆分，支持在线阅读 |
| **模型管理** | 统一管理本地模型与云端 API（阿里云、智谱、火山引擎等），按需加载/卸载 |
| **系统监控** | 实时 CPU / 内存 / 磁盘 / GPU 资源监控，WebSocket 日志推送 |

## 技术栈

### 后端
- **Web 框架**: FastAPI + Uvicorn
- **AI 模型**: PyTorch, Transformers, CosyVoice3, DreamLite, Qwen3.5, Qwen3-Embedding
- **数据库**: SQLite (WAL 模式)
- **模型调度**: ModelScope 模型下载与管理
- **桌面 GUI**: Kivy (可选，服务端日志界面)

### 前端
- **UI 框架**: Bootstrap 5 + Font Awesome
- **通信**: WebSocket + Fetch API
- **页面**: 单页应用（主页 / 剧本编辑器 / 电子书阅读器）

### 支持的 AI 平台

| 平台 | 能力 | 状态 |
|------|------|------|
| 本地模型 | 文本 / TTS / 文生图 / Embedding | ✅ |
| 阿里云 (DashScope) | 文本 / TTS / 文生图 | ✅ |
| 智谱 AI | 文本 | ✅ |
| 火山引擎 (豆包) | 文本 | ✅ |
| 百度文心 | 文本 | 可选 |
| DeepSeek | 文本 | 可选 |
| Google Gemini | 文本 | 可选 |

## 项目结构

```
CosyChat/
├── backend/                 # 后端服务
│   ├── api/                 #   REST API 路由层
│   ├── agents/              #   智能体管理与数据
│   ├── core/                #   核心模块（模型执行、配置管理、全局管理）
│   ├── models/              #   模型封装（CosyVoice、DreamLite、Qwen 等）
│   ├── repositories/        #   数据访问层（SQLite）
│   ├── services/            #   业务逻辑层
│   │   └── writing_pipeline/  # 网文写作流水线
│   ├── utils/               #   工具类（日志、FFmpeg、代理等）
│   ├── widgets/             #   Kivy GUI 组件
│   ├── main.py              #   FastAPI 应用入口
│   ├── start_server.py      #   服务启动脚本（含 Kivy GUI）
│   └── kivy_app.py          #   Kivy 桌面应用
├── frontend/                # 前端静态资源
│   ├── index.html           #   主页面
│   ├── script_editor.html   #   剧本编辑器
│   ├── ebook_reader.html    #   电子书阅读器
│   └── assets/              #   CSS / JS / 字体
├── config/                  # 系统配置
│   └── system_config.json   #   模型路径、平台密钥、能力配置
├── pretrained_models/       # 本地预训练模型
│   ├── cosyvoice/           #   CosyVoice3 语音合成
│   ├── dreamlite/           #   DreamLite 文生图
│   ├── qwen/                #   Qwen 文本生成
│   └── qwen_embedding/      #   Qwen 文本向量化
├── media/                   # 媒体资源（音频/图片/文档/视频）
├── docs/                    # 项目文档
└── version.json             # 版本号
```

## 架构设计

```
┌─────────────────────────────────────────────────┐
│                   前端 (HTML/JS)                  │
│   index.html │ script_editor.html │ ebook_reader  │
└──────────────────────┬──────────────────────────┘
                       │ HTTP / WebSocket
┌──────────────────────▼──────────────────────────┐
│                API 层 (FastAPI)                   │
│  system │ agents │ text_chat │ audio │ books ...  │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              Service 层 (业务逻辑)                │
│  chat │ audio │ ebook_library │ webnovel_service  │
│  script │ media_manager │ vector_store            │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│           Core 层 (模型统一调度)                   │
│         ModelExecutor ← 全局管理器                │
│  QwenModel │ CosyVoiceModel │ DreamLiteModel     │
│  QwenEmbeddingModel                             │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│            Repository 层 (数据持久化)              │
│              SQLite (cosychat.db)                 │
└─────────────────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Python >= 3.13
- CUDA 兼容的 GPU（推荐，用于本地模型推理）
- FFmpeg（用于音频处理）

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd CosyChat

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate     # Windows

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

服务默认运行在 `http://localhost:8000`，可在 `config/system_config.json` 的 `system.port` 修改端口。

## 主要 API

| 端点 | 说明 |
|------|------|
| `GET /api/system/status` | 系统状态与资源监控 |
| `POST /api/chat/stream` | 流式文本对话 |
| `POST /api/audio/synthesize` | 语音合成 |
| `POST /api/image/generate` | 文生图 |
| `POST /api/asr/transcribe` | 语音识别 |
| `POST /api/books/library/upload` | 电子书上传入库 |
| `GET /api/books/library` | 电子书列表 |
| `GET/POST /api/agents` | 智能体管理 |
| `GET/POST /api/books/scripts` | 网文写作相关接口 |
| `WS /ws` | WebSocket 实时日志推送 |

完整 API 调用链详见 [docs/api_call_chains.md](docs/api_call_chains.md)。

## 文档

- [API 调用链文档](docs/api_call_chains.md) — 前端页面与后端 API 的调用关系
- [任务书](TASK_BOOK.md) — 网文写作功能开发计划

## 许可证

MIT License
