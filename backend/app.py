"""ZHKU Campus Agent 后端入口。

提供 FastAPI 应用实例、路由挂载和健康检查。

直接运行本文件即可启动服务：
    python backend/app.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

# 允许 `python backend/app.py` 直接运行时正确解析 backend 包
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import admin, auth, chat, interview, resources, resume, schedule, search, upload
from backend.cache.qa_file_cache import qa_cache
from backend.config import settings


def _configure_logging() -> None:
    """确保 backend 阶段日志在直接运行和 Uvicorn 下都可见。"""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    backend_logger = logging.getLogger("backend")
    backend_logger.setLevel(level)
    if not backend_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        backend_logger.addHandler(handler)
        backend_logger.propagate = False


_configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化资源，关闭时清理。"""
    settings.ensure_dirs()
    await qa_cache.connect()
    app.state.qa_cache_status = qa_cache.status
    app.state.embedding_status = "loading"
    should_warmup = (
        settings.embedding_warmup_enabled
        and settings.embedding_warmup_mode == "blocking"
        and settings.embedding_provider == "local"
    )
    if should_warmup:
        warmup_started_at = time.perf_counter()
        try:
            from backend.rag.embedder import get_embedder

            await asyncio.to_thread(get_embedder().embed_one, "仲恺校园服务启动预热")
            app.state.embedding_status = "ready"
            logger.info(
                "embedding_warmup status=success model=%s duration_ms=%.1f",
                settings.embedding_model,
                (time.perf_counter() - warmup_started_at) * 1000,
            )
        except Exception as exc:
            logger.warning(
                "embedding_warmup status=failed error_type=%s duration_ms=%.1f",
                type(exc).__name__,
                (time.perf_counter() - warmup_started_at) * 1000,
            )
            app.state.embedding_status = "failed"
    else:
        app.state.embedding_status = "disabled"
    # 确保用户相关表存在（兼容已有库未跑全量 schema 的情况）
    try:
        from backend.database.models import (
            CampusAdviceCache,
            CampusWeatherCache,
            ChatMessage,
            ChatSession,
            ResumeProfile,
            User,
            UserDocument,
            UserSchedule,
        )
        from backend.database.session import engine

        for table in (
            User.__table__,
            ChatSession.__table__,
            ChatMessage.__table__,
            ResumeProfile.__table__,
            UserSchedule.__table__,
            CampusWeatherCache.__table__,
            CampusAdviceCache.__table__,
            UserDocument.__table__,
        ):
            table.create(bind=engine, checkfirst=True)
    except Exception as e:
        print(f"[Startup] 用户相关表初始化跳过: {e}")
    yield
    await qa_cache.close()


app = FastAPI(
    title="ZHKU Campus Agent",
    description="仲恺校园信息服务智能体后端 API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS（开发期允许前端跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由挂载
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(resources.router, prefix="/api/resources", tags=["resources"])
app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(resume.router, prefix="/api/resume", tags=["resume"])
app.include_router(interview.router, prefix="/api/interview", tags=["interview"])
app.include_router(schedule.router, prefix="/api/schedule", tags=["schedule"])


@app.get("/health", tags=["meta"])
async def health() -> dict:
    """健康检查。"""
    return {
        "status": "ok",
        "service": "zhku-campus-agent",
        "version": "0.1.0",
        "embedding_status": getattr(app.state, "embedding_status", "loading"),
        "qa_cache_status": getattr(app.state, "qa_cache_status", qa_cache.status),
    }


@app.get("/", tags=["meta"])
async def root() -> dict:
    """根路径信息。"""
    return {
        "service": "ZHKU Campus Agent",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/api/stats", tags=["meta"])
async def stats() -> dict:
    """知识库统计数据。"""
    from backend.database.models import UserDocument
    from backend.database.session import SessionLocal
    from backend.rag.vector_store import get_vector_store

    store = get_vector_store()
    campus_chunks = store.count_documents(collection="zhku")
    shared_doc_chunks = store.count_documents(collection="document")
    user_doc_chunks = store.count_documents(collection="user_docs")
    doc_chunks = shared_doc_chunks + user_doc_chunks

    uploaded_docs = 0
    departments: set[str] = set()
    try:
        with SessionLocal() as db:
            rows = db.query(UserDocument).all()
            uploaded_docs = len(rows)
            departments = {r.department or "文档库" for r in rows}
    except Exception:
        pass

    return {
        "campus_chunks": campus_chunks,
        "document_chunks": doc_chunks,
        "uploaded_docs": uploaded_docs,
        "total_chunks": campus_chunks + doc_chunks,
        "tools": ["major_search", "download_search", "contact_search", "service_link_search"],
        "departments": list(departments),
    }


if __name__ == "__main__":
    import os

    import uvicorn

    # 统一工作目录，避免 IDE 从 backend/ 启动时相对路径与 .env 解析异常
    os.chdir(_PROJECT_ROOT)

    reload_dirs = [
        (_PROJECT_ROOT / directory.strip()).resolve()
        for directory in settings.app_reload_dirs.split(",")
        if directory.strip()
    ]

    uvicorn.run(
        "backend.app:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_reload_enabled,
        reload_dirs=reload_dirs or [_PROJECT_ROOT / "backend"],
        log_level=settings.log_level.lower(),
    )
