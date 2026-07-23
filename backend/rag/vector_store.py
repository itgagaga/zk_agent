"""向量库封装。

封装 Chroma 操作，提供知识库集合、文档集合的读写接口。
"""
from __future__ import annotations

from typing import Any

from backend.config import settings


class VectorStore:
    """向量库封装。"""

    def __init__(self) -> None:
        self.persist_path = str(settings.vector_store_path)
        self.collection_zhku = settings.chroma_collection_zhku
        self.collection_doc = settings.chroma_collection_document
        self._client: Any = None
        self._zhku_collection: Any = None
        self._doc_collection: Any = None

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

    def add_documents(
        self,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, Any]],
        collection: str = "zhku",
    ) -> None:
        """写入文档到向量库。"""
        from backend.rag.embedder import get_embedder

        self._init_client()
        target = self._zhku_collection if collection == "zhku" else self._doc_collection
        embeddings = get_embedder().embed(texts)
        target.upsert(ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings)

    def query(
        self,
        text: str,
        top_k: int | None = None,
        where: dict[str, Any] | None = None,
        collection: str = "zhku",
    ) -> list[dict[str, Any]]:
        """检索向量库。"""
        from backend.rag.embedder import get_embedder

        self._init_client()
        target = self._zhku_collection if collection == "zhku" else self._doc_collection
        embedding = get_embedder().embed_one(text)
        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": top_k or settings.rag_top_k,
        }
        if where:
            kwargs["where"] = where
        result = target.query(**kwargs)
        return self._format_result(result)

    def delete_documents(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        collection: str = "document",
    ) -> None:
        """从向量库删除文档，支持按 id 或按元数据 where 过滤。"""
        self._init_client()
        target = self._zhku_collection if collection == "zhku" else self._doc_collection
        kwargs: dict[str, Any] = {}
        if ids:
            kwargs["ids"] = ids
        if where:
            kwargs["where"] = where
        if not kwargs:
            return
        target.delete(**kwargs)

    def count_documents(self, where: dict[str, Any] | None = None, collection: str = "document") -> int:
        """统计文档集合中的 chunk 数量，支持按 where 过滤。"""
        self._init_client()
        target = self._zhku_collection if collection == "zhku" else self._doc_collection
        if where:
            result = target.get(where=where)
            return len(result.get("ids", []))
        return target.count()

    @staticmethod
    def _format_result(result: dict[str, Any]) -> list[dict[str, Any]]:
        """格式化 Chroma 返回。"""
        if not result or not result.get("documents"):
            return []
        docs = result["documents"][0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]
        hits: list[dict[str, Any]] = []
        for doc, meta, dist in zip(docs, metas, dists):
            hits.append(
                {
                    "snippet": doc,
                    "title": meta.get("title", ""),
                    "department": meta.get("department"),
                    "url": meta.get("source_url", ""),
                    "publish_date": meta.get("publish_date"),
                    "score": 1.0 - float(dist),
                    "metadata": meta,
                }
            )
        return hits


# 全局单例
_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
