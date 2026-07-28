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

        用户上传文档（如培养方案 PDF）常按 500 字切分为多段，且向量相似度
        整体偏低；因此对私有文档使用更低阈值、更大 top_k，并在命中后对小
        文档（片段数 ≤ rag_doc_full_fetch_max_chunks）拉取全文片段。
        """
        is_user_doc = user_id is not None
        collection = "user_docs" if is_user_doc else "document"
        effective_top_k = top_k or (
            settings.rag_doc_top_k if is_user_doc else self.top_k
        )
        threshold = (
            settings.rag_doc_score_threshold if is_user_doc else self.score_threshold
        )

        user_where: dict[str, Any] | None = where
        if is_user_doc:
            user_where = {"user_id": int(user_id)}
            if where:
                user_where = {"$and": [user_where, where]}

        # 多取一些候选，便于后续扩展与小文档全文拉取
        query_top_k = effective_top_k * 3 if is_user_doc else effective_top_k
        hits = self.store.query(
            text=query,
            top_k=query_top_k,
            where=user_where,
            collection=collection,
        )
        hits = [h for h in hits if h.get("score", 0) >= threshold]

        if is_user_doc and hits:
            hits, full_doc = self._enrich_user_doc_hits(hits, effective_top_k)
            if full_doc:
                return hits

        return hits[:effective_top_k]

    def _enrich_user_doc_hits(
        self,
        hits: list[dict[str, Any]],
        limit: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        """对小文档拉取全部片段，避免培养方案后半段（专业课程表）被漏召回。"""
        doc_ids: set[str] = set()
        for hit in hits:
            doc_id = (hit.get("metadata") or {}).get("doc_id")
            if doc_id:
                doc_ids.add(doc_id)

        merged: dict[str, dict[str, Any]] = {}
        for hit in hits:
            key = hit.get("chunk_id") or str(id(hit))
            merged[key] = hit

        max_chunks = settings.rag_doc_full_fetch_max_chunks
        full_doc = False
        for doc_id in doc_ids:
            chunk_count = self.store.count_documents(
                where={"doc_id": doc_id},
                collection="user_docs",
            )
            if chunk_count <= max_chunks:
                full_doc = True
                for chunk in self.store.get_chunks_by_doc_id(doc_id, collection="user_docs"):
                    merged[chunk["chunk_id"]] = chunk

        ordered = sorted(
            merged.values(),
            key=lambda h: (
                (h.get("metadata") or {}).get("doc_id", ""),
                h.get("chunk_index") if h.get("chunk_index") is not None else 9999,
                -(h.get("score") or 0),
            ),
        )
        if full_doc:
            return ordered, True
        return ordered[:limit], False
