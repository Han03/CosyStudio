from .system import router as system_router
from .models import router as models_router
from .agents import router as agents_router
from .audio_synthesize import router as chat_router
from .websocket import router as websocket_router
from .media import router as media_router
from .image_generate import router as dreamlite_router

__all__ = [
    "system_router",
    "models_router",
    "agents_router",
    "chat_router",
    "websocket_router",
    "media_router",
    "dreamlite_router"
]
