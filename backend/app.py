"""ZHKU Campus Agent 后端入口。

提供 FastAPI 应用实例、路由挂载和健康检查。
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import admin, auth, chat, interview, resources, resume, schedule, search, upload
from backend.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化资源，关闭时清理。"""
    settings.ensure_dirs()
    # 确保用户相关表存在（兼容已有库未跑全量 schema 的情况）
    try:
        from backend.database.models import (
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
            UserDocument.__table__,
        ):
            table.create(bind=engine, checkfirst=True)
    except Exception as e:
        print(f"[Startup] 用户相关表初始化跳过: {e}")
    yield
    # TODO: 关闭资源


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
    return {"status": "ok", "service": "zhku-campus-agent", "version": "0.1.0"}


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
