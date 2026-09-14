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


def resolve_project_path(p: str) -> str:
    """项目内路径统一解析为绝对路径（供运行时使用）。

    - 空 / URL → 原样返回
    - 绝对路径存在 → 原样返回
    - 绝对路径不存在 → 若路径含 '/cosystudio/' 前缀，按项目根重组（容错迁移/换盘）
    - 相对路径 → 拼接 PROJECT_ROOT（以 '/' 或 '\\' 分隔均可）
    """
    if not p:
        return ""
    if p.startswith(("http://", "https://", "data:")):
        return p
    if os.path.isabs(p):
        if os.path.exists(p):
            return p
        norm = p.replace("\\", "/").lower()
        marker = "/cosystudio/"
        idx = norm.rfind(marker)
        if idx >= 0:
            # 用原始字符串按同索引切分，保留大小写
            orig = p.replace("\\", "/")
            rel = orig[idx + len(marker):].replace("/", os.sep)
            cand = os.path.join(PROJECT_ROOT, rel)
            if os.path.exists(cand):
                return cand
        return p
    return os.path.normpath(os.path.join(PROJECT_ROOT, p.replace("/", os.sep)))


def to_project_relpath(p: str) -> str:
    """绝对路径 → 项目根相对路径（POSIX 分隔符）。不在项目内则原样返回。"""
    if not p:
        return ""
    try:
        rp = os.path.relpath(os.path.abspath(p), PROJECT_ROOT)
    except Exception:
        return p
    if rp.startswith(".."):
        return p
    return rp.replace("\\", "/")
