"""中间件统一注册。"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# 上传大小限制常量
MAX_UPLOAD_SIZE = 5 * 1024 * 1024
EBOOK_UPLOAD_PATH = "/api/books/library/upload"
EBOOK_MAX_UPLOAD_SIZE = 50 * 1024 * 1024
ASR_UPLOAD_PATH = "/api/asr/transcribe"
ASR_MAX_UPLOAD_SIZE = 25 * 1024 * 1024


def setup_middleware(app: FastAPI):
    """注册所有中间件。"""
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 上传大小限制
    @app.middleware("http")
    async def limit_upload_size(request: Request, call_next):
        if request.method == "POST":
            content_length = request.headers.get("content-length")
            if content_length:
                cl = int(content_length)
                path = request.url.path
                if path == EBOOK_UPLOAD_PATH:
                    if cl > EBOOK_MAX_UPLOAD_SIZE:
                        raise HTTPException(status_code=413, detail=f"电子书大小超过{EBOOK_MAX_UPLOAD_SIZE/1024/1024:.0f}MB限制")
                elif path == ASR_UPLOAD_PATH:
                    if cl > ASR_MAX_UPLOAD_SIZE:
                        raise HTTPException(status_code=413, detail=f"音频文件大小超过{ASR_MAX_UPLOAD_SIZE/1024/1024:.0f}MB限制")
                elif cl > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail=f"上传文件大小超过{MAX_UPLOAD_SIZE/1024/1024:.0f}MB限制")
        return await call_next(request)
