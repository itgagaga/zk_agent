"""检索 API。

直接访问 RAG 检索、新闻公告检索等底层能力，便于前端独立调试。
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.rag.retriever import RAGRetriever

router = APIRouter()

# 全局检索器单例
_retriever = RAGRetriever()


class SearchHit(BaseModel):
    """检索命中项。"""

    title: str
    department: str | None = None
    url: str
    publish_date: str | None = None
    snippet: str
    score: float | None = None


class SearchResponse(BaseModel):
    """检索响应。"""

    query: str
    hits: list[SearchHit] = Field(default_factory=list)
    total: int = 0


@router.get("/rag", response_model=SearchResponse)
async def rag_search(
    q: str = Query(..., description="检索关键词"),
    top_k: int = Query(default=5, ge=1, le=20),
) -> SearchResponse:
    """官网 RAG 检索。"""
    hits = await _retriever.search(q, top_k=top_k)
    return SearchResponse(
        query=q,
        hits=[
            SearchHit(
                title=h.get("title", ""),
                department=h.get("department"),
                url=h.get("url", ""),
                publish_date=h.get("publish_date"),
                snippet=h.get("snippet", ""),
                score=h.get("score"),
            )
            for h in hits
        ],
        total=len(hits),
    )


@router.get("/news", response_model=SearchResponse)
async def news_search(
    q: str = Query(..., description="新闻公告关键词"),
    category: str | None = Query(default=None, description="栏目：学校要闻/通知公告/校园快讯"),
    top_k: int = Query(default=10, ge=1, le=50),
) -> SearchResponse:
    """新闻公告检索（暂未实现）。"""
    return SearchResponse(query=q, hits=[], total=0)


@router.get("/documents", response_model=SearchResponse)
async def document_search(
    q: str = Query(..., description="文档检索关键词"),
    department: str | None = Query(default=None, description="来源部门过滤"),
    top_k: int = Query(default=5, ge=1, le=20),
) -> SearchResponse:
    """智能文档检索。"""
    # 同时查通用知识库和文档库（第一阶段资料都在 campus 集合）
    hits = await _retriever.search(q, top_k=top_k)
    doc_hits = await _retriever.search_documents(q, top_k=top_k)
    all_hits = hits + doc_hits
    # 部门过滤
    if department:
        all_hits = [h for h in all_hits if department in (h.get("department") or "")]
    # 按分数去重排序
    seen: set[str] = set()
    unique: list[dict] = []
    for h in sorted(all_hits, key=lambda x: x.get("score", 0), reverse=True):
        key = h.get("url", "") + h.get("title", "")
        if key not in seen:
            seen.add(key)
            unique.append(h)
    return SearchResponse(
        query=q,
        hits=[
            SearchHit(
                title=h.get("title", ""),
                department=h.get("department"),
                url=h.get("url", ""),
                publish_date=h.get("publish_date"),
                snippet=h.get("snippet", ""),
                score=h.get("score"),
            )
            for h in unique[:top_k]
        ],
        total=len(unique),
    )
