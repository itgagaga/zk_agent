"""检索 API。

直接访问 RAG 检索、新闻公告检索等底层能力，便于前端独立调试。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from backend.auth.deps import get_current_user_optional
from backend.database.models import User
from backend.rag.retriever import RAGRetriever
from backend.rag.contracts import Evidence, EvidenceBundle
from backend.rag.evidence_gate import EvidenceGate

router = APIRouter()

_retriever = RAGRetriever()


class SearchHit(BaseModel):
    """检索命中项。"""

    title: str
    department: str | None = None
    url: str
    publish_date: str | None = None
    snippet: str
    score: float | None = None
    chunk_id: str | None = None


class SearchResponse(BaseModel):
    """检索响应。"""

    query: str
    hits: list[SearchHit] = Field(default_factory=list)
    total: int = 0
    retrieval_summary: dict | None = None


@router.get("/rag", response_model=SearchResponse)
async def rag_search(
    q: str = Query(..., description="检索关键词"),
    top_k: int = Query(default=5, ge=1, le=20),
) -> SearchResponse:
    """官网 RAG 检索。"""
    hits = await _retriever.search(q, top_k=top_k)
    bundle = EvidenceBundle(
        query=q,
        evidences=[Evidence.from_rag_hit(hit) for hit in hits],
        retrievers=["campus_rag"],
    )
    gate = EvidenceGate()
    bundle.evidences = gate.rank(q, bundle.evidences)
    assessment = gate.assess(bundle)
    ordered_hits = [evidence.raw for evidence in bundle.evidences]
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
                chunk_id=h.get("chunk_id"),
            )
            for h in ordered_hits
        ],
        total=len(ordered_hits),
        retrieval_summary={
            "retrievers": ["campus_rag"],
            "evidence_assessment": assessment.model_dump(),
        },
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
    current_user: User | None = Depends(get_current_user_optional),
) -> SearchResponse:
    """智能文档检索（登录用户检索私有文档；未登录仅查共享文档库）。"""
    hits = await _retriever.search(q, top_k=top_k)
    doc_hits = await _retriever.search_documents(
        q,
        top_k=top_k,
        user_id=current_user.id if current_user else None,
    )
    all_hits = hits + doc_hits
    if department:
        all_hits = [h for h in all_hits if department in (h.get("department") or "")]
    seen: set[str] = set()
    unique: list[dict] = []
    for h in sorted(all_hits, key=lambda x: x.get("score", 0), reverse=True):
        key = h.get("url", "") + h.get("title", "") + (h.get("snippet") or "")[:40]
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
                chunk_id=h.get("chunk_id"),
            )
            for h in unique[:top_k]
        ],
        total=len(unique[:top_k]),
    )
