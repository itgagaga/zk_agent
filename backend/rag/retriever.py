"""RAG 检索器。

封装 RAG 检索流程：向量化 → 向量库检索 → 过滤 → Parent 扩展 → 返回命中。
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
        effective_top_k = top_k or self.top_k
        query_top_k = max(effective_top_k * 4, effective_top_k + 8)
        hits = self.store.query(
            text=query,
            top_k=query_top_k,
            where=where,
            collection="zhku",
        )
        keyword_search = getattr(self.store, "keyword_search", None)
        if keyword_search is not None:
            hits = self._merge_hits(
                hits,
                keyword_search(
                    text=query,
                    top_k=query_top_k,
                    where=where,
                    collection="zhku",
                ),
            )
        hits = [h for h in hits if h.get("score", 0) >= self.score_threshold]
        hits = self._expand_parent_hits(hits, collection="zhku")
        return self._sort_and_dedupe(hits)[:effective_top_k]

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

        命中 Child 片段时会扩展为完整 Parent 节；小文档仍会拉取全部片段。
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

        query_top_k = max(effective_top_k * 4, effective_top_k + 8)
        hits = self.store.query(
            text=query,
            top_k=query_top_k,
            where=user_where,
            collection=collection,
        )
        keyword_search = getattr(self.store, "keyword_search", None)
        if keyword_search is not None:
            hits = self._merge_hits(
                hits,
                keyword_search(
                    text=query,
                    top_k=query_top_k,
                    where=user_where,
                    collection=collection,
                ),
            )
        hits = [h for h in hits if h.get("score", 0) >= threshold]
        hits = self._expand_parent_hits(hits, collection=collection, user_id=user_id)

        if is_user_doc and hits:
            hits, full_doc = self._enrich_user_doc_hits(
                hits, effective_top_k, user_id=user_id
            )
            if full_doc:
                return hits

        return hits[:effective_top_k]

    def _expand_parent_hits(
        self,
        hits: list[dict[str, Any]],
        *,
        collection: str,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Child 命中时合并同一 Parent 下的全部片段，返回完整章节上下文。"""
        if not hits:
            return hits

        merged: dict[str, dict[str, Any]] = {}
        order: list[str] = []

        for hit in hits:
            meta = hit.get("metadata") or {}
            chunk_role = meta.get("chunk_role", "")
            parent_id = meta.get("parent_id", "")

            if chunk_role == "child" and parent_id:
                siblings = self.store.get_chunks_by_parent_id(
                    parent_id,
                    user_id=user_id,
                    collection=collection,
                )
                if len(siblings) > 1:
                    best_score = hit.get("score", 0)
                    combined_snippet = "\n".join(
                        s.get("snippet", "") for s in siblings if s.get("snippet")
                    )
                    key = f"parent:{parent_id}"
                    if key not in merged:
                        order.append(key)
                    merged[key] = {
                        **hit,
                        "snippet": combined_snippet,
                        "score": best_score,
                        "metadata": {**meta, "chunk_role": "parent_expanded"},
                    }
                    continue

            key = hit.get("chunk_id") or str(id(hit))
            if key not in merged:
                order.append(key)
            if key not in merged or hit.get("score", 0) > merged[key].get("score", 0):
                merged[key] = hit

        return [merged[k] for k in order if k in merged]

    def _enrich_user_doc_hits(
        self,
        hits: list[dict[str, Any]],
        limit: int,
        *,
        user_id: int | None = None,
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
            scoped_user_id = user_id
            if scoped_user_id is None:
                scoped_user_id = next(
                    (
                        (hit.get("metadata") or {}).get("user_id")
                        for hit in hits
                        if (hit.get("metadata") or {}).get("user_id") is not None
                    ),
                    None,
                )
            where: dict[str, Any] = {"doc_id": doc_id}
            if scoped_user_id is not None:
                where["user_id"] = int(scoped_user_id)
            chunk_count = self.store.count_documents(
                where=where,
                collection="user_docs",
            )
            if chunk_count <= max_chunks:
                full_doc = True
                for chunk in self.store.get_chunks_by_doc_id(
                    doc_id, user_id=scoped_user_id, collection="user_docs"
                ):
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

    @staticmethod
    def _merge_hits(*hit_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """合并 dense/lexical 候选，按稳定 chunk id 去重并保留最高分。"""
        merged: dict[str, dict[str, Any]] = {}
        for hits in hit_lists:
            for hit in hits or []:
                key = hit.get("chunk_id") or hit.get("id") or str(id(hit))
                previous = merged.get(key)
                if previous is None or float(hit.get("score") or 0) > float(previous.get("score") or 0):
                    merged[key] = hit
        return list(merged.values())

    @classmethod
    def _sort_and_dedupe(cls, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            cls._merge_hits(hits),
            key=lambda hit: (-float(hit.get("score") or 0), hit.get("chunk_id") or ""),
        )
