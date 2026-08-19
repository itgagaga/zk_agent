"""检索与证据融合的稳定数据契约。

各检索器可以保留自己的原始字段，但进入答案生成前统一转换为
``Evidence``。这样排序、去重、引用和前端元数据不再依赖某个 Agent 的
内部字典结构。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


EvidenceKind = Literal["rag", "document", "tool", "api"]


class Evidence(BaseModel):
    """单条可引用证据。"""

    evidence_id: str
    kind: EvidenceKind
    retriever: str
    title: str = ""
    snippet: str = ""
    url: str = ""
    source_page_url: str = ""
    file_url: str = ""
    score: float = 0.0
    rank: int | None = None
    doc_id: str | None = None
    chunk_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_rag_hit(cls, hit: dict[str, Any], *, retriever: str = "campus_rag") -> "Evidence":
        meta = dict(hit.get("metadata") or {})
        chunk_id = hit.get("chunk_id") or meta.get("chunk_id")
        doc_id = hit.get("doc_id") or meta.get("doc_id")
        evidence_id = str(chunk_id or doc_id or hit.get("url") or hit.get("title") or id(hit))
        return cls(
            evidence_id=evidence_id,
            kind="document" if retriever == "user_docs" or meta.get("user_id") is not None else "rag",
            retriever=retriever,
            title=str(hit.get("title") or meta.get("title") or ""),
            snippet=str(hit.get("snippet") or ""),
            url=str(hit.get("url") or meta.get("source_url") or ""),
            source_page_url=str(hit.get("source_page_url") or ""),
            score=float(hit.get("score") or 0.0),
            rank=hit.get("rank"),
            doc_id=str(doc_id) if doc_id is not None else None,
            chunk_id=str(chunk_id) if chunk_id is not None else None,
            metadata=meta,
            raw=dict(hit),
        )

    @classmethod
    def from_tool_item(cls, item: dict[str, Any], *, tool: str) -> "Evidence":
        title = str(item.get("title") or item.get("name") or "")
        url = str(item.get("url") or item.get("source_page_url") or "")
        file_url = str(item.get("file_url") or "")
        stable = (
            item.get("evidence_id")
            or item.get("id")
            or file_url
            or url
            or f"{title}|{item.get('phone', '')}|{item.get('address', '')}"
        )
        return cls(
            evidence_id=f"{tool}:{stable}",
            kind="api" if tool in {"map_route", "weather_search"} else "tool",
            retriever=tool,
            title=title,
            snippet=str(
                item.get("snippet")
                or item.get("summary")
                or item.get("service_scope")
                or item.get("description")
                or ""
            ),
            url=url,
            source_page_url=str(item.get("source_page_url") or ""),
            file_url=file_url,
            score=float(item.get("score") or 0.0),
            rank=item.get("rank"),
            metadata=dict(item.get("metadata") or {}),
            raw=dict(item),
        )

    def to_source_dict(self) -> dict[str, Any]:
        """转换为现有 AnswerGenerator/frontend 使用的来源字段。"""
        return {
            "title": self.title,
            "department": self.metadata.get("department"),
            "url": self.file_url or self.url or self.source_page_url,
            "publish_date": self.metadata.get("publish_date"),
            "snippet": self.snippet,
            "evidence_id": self.evidence_id,
            "retriever": self.retriever,
            "score": self.score,
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
        }


class EvidenceBundle(BaseModel):
    """一次查询的规划、检索和融合结果。"""

    query: str
    evidences: list[Evidence] = Field(default_factory=list)
    retrievers: list[str] = Field(default_factory=list)
    coverage: float = 0.0
    independent_source_count: int = 0
    fallback: bool = False
    trace_id: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    def sources(self) -> list[dict[str, Any]]:
        return [e.to_source_dict() for e in self.evidences]
