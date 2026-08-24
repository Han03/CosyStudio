import os
import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

# ============================================================
# Python 路径初始化（必须最先执行）
# ============================================================
_current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _current_dir)
sys.path.insert(1, os.path.join(_current_dir, 'models'))

# ============================================================
# 模块导入
# ============================================================
from middleware import setup_middleware
from core.lifecycle import register_startup_hooks
from core.paths import OUTPUT_DIR, AGENTS_DATA_DIR, FRONTEND_DIR
from core.global_manager import global_manager

from api.system import router as system_router
from api.models import router as models_router
from api.agents import router as agents_router
from api.text_chat import router as text_chat_router
from api.websocket import router as websocket_router
from api.media import router as media_router
from api.image_generate import router as image_generate_router
from api.audio_synthesize import router as audio_synthesize_router
from api.books import router as books_router
from api.asr import router as asr_router
from api.model_capability import router as model_capability_router
from webnovel.api.routes import router as webnovel_router
from webnovel.api.integration_routes import router as webnovel_integration_router
from webnovel.api.init_routes import router as webnovel_init_router

# ============================================================
# FastAPI 应用创建
# ============================================================
app = FastAPI(title="CosyChat", description="模型服务")

setup_middleware(app)

# ============================================================
# Router 注册
# ============================================================
app.include_router(system_router)
app.include_router(models_router)
app.include_router(agents_router)
app.include_router(text_chat_router)
app.include_router(websocket_router)
app.include_router(media_router)
app.include_router(image_generate_router)
app.include_router(audio_synthesize_router)
app.include_router(books_router)
app.include_router(asr_router)
app.include_router(model_capability_router)
app.include_router(webnovel_router)
app.include_router(webnovel_integration_router)
app.include_router(webnovel_init_router)

# ============================================================
# 生命周期钩子
# ============================================================
register_startup_hooks(app)

# ============================================================
# 静态文件挂载
# ============================================================
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")
app.mount("/agents_data", StaticFiles(directory=AGENTS_DATA_DIR), name="agents_data")
app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="home")

# ============================================================
# 启动入口
# ============================================================
if __name__ == "__main__":
    try:
        from core.config_manager import get_server_port
        port = get_server_port()
    except:
        port = 8000
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
