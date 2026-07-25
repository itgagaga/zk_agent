"""ZHKU Campus Agent 后端入口。

提供 FastAPI 应用实例、路由挂载和健康检查。
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import admin, chat, resources, resume, search, upload
from backend.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化资源，关闭时清理。"""
    settings.ensure_dirs()
    # TODO: 初始化 SQLite、向量库、LLM 客户端
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
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(resources.router, prefix="/api/resources", tags=["resources"])
app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(resume.router, prefix="/api/resume", tags=["resume"])


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
    from backend.rag.vector_store import get_vector_store
    from backend.api.upload import _load_manifest

    store = get_vector_store()
    campus_chunks = store.count_documents(collection="zhku")
    doc_chunks = store.count_documents(collection="document")
    manifest = _load_manifest()

    return {
        "campus_chunks": campus_chunks,
        "document_chunks": doc_chunks,
        "uploaded_docs": len(manifest),
        "total_chunks": campus_chunks + doc_chunks,
        "tools": ["major_search", "download_search", "contact_search", "service_link_search"],
        "departments": list({d.get("department", "文档库") for d in manifest}),
    }
