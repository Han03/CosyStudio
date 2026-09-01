"""统一路径常量。

所有运行时数据目录在此集中定义，其他模块通过 import 引用，
禁止在各处硬编码 os.path.join 路径。
"""
import os

# 项目品牌名称（集中管理，所有运行时引用从此处获取）
APP_NAME = "CosyStudio"

# 项目根目录（CosyStudio/）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 运行时数据目录
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
LOG_DIR = os.path.join(DATA_DIR, "logs")
AGENTS_DATA_DIR = os.path.join(DATA_DIR, "agents")

# 第三方二进制工具
BIN_DIR = os.path.join(PROJECT_ROOT, "bin")

# 项目配置与资源（非运行时数据，保持原位）
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
MEDIA_DIR = os.path.join(PROJECT_ROOT, "media")
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
PRETRAINED_MODELS_DIR = os.path.join(PROJECT_ROOT, "pretrained_models")

# 确保核心目录存在
for _d in (DATA_DIR, CACHE_DIR, OUTPUT_DIR, LOG_DIR, AGENTS_DATA_DIR):
    os.makedirs(_d, exist_ok=True)
