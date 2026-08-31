"""向量库封装。

封装 Chroma 操作：校园知识库、共享文档库、用户私有文档库。
"""
from __future__ import annotations

from typing import Any

from backend.config import settings
from backend.rag.lexical_index import LexicalDocument, LexicalIndex


class VectorStore:
    """向量库封装。"""

    def __init__(self) -> None:
        self.persist_path = str(settings.vector_store_path)
        self.collection_zhku = settings.chroma_collection_zhku
        self.collection_doc = settings.chroma_collection_document
        self.collection_user_docs = settings.chroma_collection_user_docs
        self._client: Any = None
        self._zhku_collection: Any = None
        self._doc_collection: Any = None
        self._user_docs_collection: Any = None
        self._lexical_indexes: dict[str, LexicalIndex | None] = {
            "zhku": None,
            "document": None,
            "user_docs": None,
        }

    def _init_client(self) -> None:
        """初始化 Chroma 客户端。"""
        if self._client is not None and self._zhku_collection is not None:
            return
        import chromadb

        if self._client is None:
            self._client = chromadb.PersistentClient(path=self.persist_path)
        self._zhku_collection = self._client.get_or_create_collection(
            self.collection_zhku
        )
        self._doc_collection = self._client.get_or_create_collection(
            self.collection_doc
        )
        self._user_docs_collection = self._client.get_or_create_collection(
            self.collection_user_docs
        )

    def _target(self, collection: str) -> Any:
        self._init_client()
        if collection in ("zhku", "campus"):
            return self._zhku_collection
        if collection in ("user_docs", "zhku_user_docs"):
            return self._user_docs_collection
        return self._doc_collection

    def add_documents(
        self,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, Any]],
        collection: str = "zhku",
    ) -> None:
        """写入文档到向量库。"""
        from backend.rag.embedder import get_embedder

        target = self._target(collection)
        embeddings = get_embedder().embed(texts)
        target.upsert(ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings)
        self.invalidate_lexical_index(collection)

    def query(
        self,
        text: str,
        top_k: int | None = None,
        where: dict[str, Any] | None = None,
        collection: str = "zhku",
    ) -> list[dict[str, Any]]:
        """检索向量库。"""
        from backend.rag.embedder import get_embedder

        target = self._target(collection)
        embedding = get_embedder().embed_one(text)
        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": top_k or settings.rag_top_k,
        }
        if where:
            kwargs["where"] = where
        result = target.query(**kwargs)
        return self._format_result(result, ids=result.get("ids", [[]])[0])

    def keyword_search(
        self,
        *,
        text: str,
        top_k: int | None = None,
        where: dict[str, Any] | None = None,
        collection: str = "zhku",
    ) -> list[dict[str, Any]]:
        """使用中文 BM25 执行词法召回。"""
        target = self._target(collection)
        kwargs: dict[str, Any] = {"include": ["documents", "metadatas"]}
        if where:
            kwargs["where"] = where
        result = target.get(**kwargs)
        ids = result.get("ids") or []
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
        documents = [
            LexicalDocument(doc_id=str(chunk_id), text=str(doc or ""), metadata=dict(meta or {}))
            for chunk_id, doc, meta in zip(ids, docs, metas)
        ]
        key = self._lexical_collection_key(collection)
        index = self._lexical_indexes.get(key)
        if index is None or where is not None:
            if where is None:
                index = LexicalIndex(documents)
                self._lexical_indexes[key] = index
            else:
                # Chroma 已按 where 过滤，临时索引只包含本次授权候选。
                index = LexicalIndex(documents)
        candidate_ids = {document.doc_id for document in documents} if where is not None else None
        return index.search(
            text,
            top_k=top_k or settings.rag_top_k,
            candidate_ids=candidate_ids,
        )

    def invalidate_lexical_index(self, collection: str) -> None:
        """写入/删除后使对应 collection 的 BM25 索引失效。"""
        self._lexical_indexes[self._lexical_collection_key(collection)] = None

    def _lexical_collection_key(self, collection: str) -> str:
        if collection in ("zhku", "campus"):
            return "zhku"
        if collection in ("user_docs", "zhku_user_docs"):
            return "user_docs"
        return "document"

    def delete_documents(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        collection: str = "document",
    ) -> None:
        """从向量库删除文档，支持按 id 或按元数据 where 过滤。"""
        target = self._target(collection)
        kwargs: dict[str, Any] = {}
        if ids:
            kwargs["ids"] = ids
        if where:
            kwargs["where"] = where
        if not kwargs:
            return
        target.delete(**kwargs)
        self.invalidate_lexical_index(collection)

    def count_documents(self, where: dict[str, Any] | None = None, collection: str = "document") -> int:
        """统计文档集合中的 chunk 数量，支持按 where 过滤。"""
        target = self._target(collection)
        if where:
            result = target.get(where=where)
            return len(result.get("ids", []))
        return target.count()

    def get_chunks_by_parent_id(
        self,
        parent_id: str,
        doc_id: str | None = None,
        user_id: int | None = None,
        collection: str = "zhku",
    ) -> list[dict[str, Any]]:
        """按 parent_id 取回同一 Parent 下的全部 chunk（按片段序号排序）。"""
        target = self._target(collection)
        clauses: list[dict[str, Any]] = [{"parent_id": parent_id}]
        if doc_id:
            clauses.append({"doc_id": doc_id})
        if user_id is not None:
            clauses.append({"user_id": int(user_id)})
        where: dict[str, Any] = clauses[0] if len(clauses) == 1 else {"$and": clauses}
        result = target.get(
            where=where,
            include=["documents", "metadatas"],
        )
        ids = result.get("ids") or []
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
        hits: list[dict[str, Any]] = []
        for chunk_id, doc, meta in zip(ids, docs, metas):
            chunk_index = meta.get("chunk_index")
            if chunk_index is None:
                chunk_index = _chunk_index_from_id(chunk_id)
            hits.append(
                {
                    "snippet": doc,
                    "title": meta.get("title", ""),
                    "department": meta.get("department"),
                    "url": meta.get("source_url", ""),
                    "publish_date": meta.get("publish_date"),
                    "score": 0.5,
                    "metadata": meta,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_index,
                }
            )
        hits.sort(key=lambda h: (h.get("chunk_index") or 0, h.get("chunk_id") or ""))
        return hits

    def get_chunks_by_doc_id(
        self,
        doc_id: str,
        user_id: int | None = None,
        collection: str = "user_docs",
    ) -> list[dict[str, Any]]:
        """按 doc_id 取回该文档的全部 chunk（按片段序号排序）。"""
        target = self._target(collection)
        where: dict[str, Any] = {"doc_id": doc_id}
        if user_id is not None:
            where["user_id"] = int(user_id)
        result = target.get(
            where=where,
            include=["documents", "metadatas"],
        )
        ids = result.get("ids") or []
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
        hits: list[dict[str, Any]] = []
        for chunk_id, doc, meta in zip(ids, docs, metas):
            chunk_index = _chunk_index_from_id(chunk_id)
            hits.append(
                {
                    "snippet": doc,
                    "title": meta.get("title", ""),
                    "department": meta.get("department"),
                    "url": meta.get("source_url", ""),
                    "publish_date": meta.get("publish_date"),
                    "score": 0.5,
                    "metadata": meta,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_index,
                }
            )
        hits.sort(key=lambda h: (h.get("chunk_index") or 0, h.get("chunk_id") or ""))
        return hits

    @staticmethod
    def _format_result(
        result: dict[str, Any],
        ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """格式化 Chroma 返回。"""
        if not result or not result.get("documents"):
            return []
        docs = result["documents"][0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]
        chunk_ids = ids or [""] * len(docs)
        hits: list[dict[str, Any]] = []
        for chunk_id, doc, meta, dist in zip(chunk_ids, docs, metas, dists):
            hits.append(
                {
                    "snippet": doc,
                    "title": meta.get("title", ""),
                    "department": meta.get("department"),
                    "url": meta.get("source_url", ""),
                    "publish_date": meta.get("publish_date"),
                    "score": 1.0 - float(dist),
                    "retrieval_source": "dense",
                    "metadata": meta,
                    "chunk_id": chunk_id,
                    "chunk_index": _chunk_index_from_id(chunk_id),
                }
            )
        return hits


def _chunk_index_from_id(chunk_id: str) -> int:
    """从 chunk id（如 ud_xxx_3）解析片段序号。"""
    if not chunk_id or "_" not in chunk_id:
        return 0
    tail = chunk_id.rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else 0


# 全局单例
_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
