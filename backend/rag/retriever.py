"""RAG 检索器。

封装 RAG 检索流程：向量化 → 向量库检索 → 过滤 → 返回命中。
"""
from __future__ import annotations

from typing import Any

from backend.config import settings
from backend.rag.vector_store import get_vector_store


class RAGRetriever:
    """RAG 检索器。"""

    def __init__(self) -> None:
        self.store = get_vector_store()
        self.top_k = settings.rag_top_k
        self.score_threshold = settings.rag_score_threshold

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """官网通用 RAG 检索。"""
        hits = self.store.query(
            text=query,
            top_k=top_k or self.top_k,
            where=where,
            collection="zhku",
        )
        return [h for h in hits if h.get("score", 0) >= self.score_threshold]

    async def search_documents(
        self,
        query: str,
        top_k: int | None = None,
        where: dict[str, Any] | None = None,
        *,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """智能文档 RAG 检索。

        若提供 user_id，检索用户私有集合 zhku_user_docs 并强制过滤；
        否则检索共享文档集合（兼容旧数据 / 未登录）。
        """
        if user_id is not None:
            user_where: dict[str, Any] = {"user_id": int(user_id)}
            if where:
                user_where = {"$and": [user_where, where]}
            hits = self.store.query(
                text=query,
                top_k=top_k or self.top_k,
                where=user_where,
                collection="user_docs",
            )
        else:
            hits = self.store.query(
                text=query,
                top_k=top_k or self.top_k,
                where=where,
                collection="document",
            )
        return [h for h in hits if h.get("score", 0) >= self.score_threshold]
