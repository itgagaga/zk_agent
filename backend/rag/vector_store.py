"""向量库封装。

封装 Chroma 操作：校园知识库、共享文档库、用户私有文档库。
"""
from __future__ import annotations

from typing import Any
import re

from backend.config import settings


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
        """在候选集合上执行轻量词法召回，补足 embedding 对专名/表名的漏召回。"""
        target = self._target(collection)
        kwargs: dict[str, Any] = {"include": ["documents", "metadatas"]}
        if where:
            kwargs["where"] = where
        result = target.get(**kwargs)
        ids = result.get("ids") or []
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
        query = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text).lower()
        # The institution name appears on almost every campus page and would
        # otherwise create a large, arbitrary tie set. Keep the subject terms.
        query = query.replace("仲恺农业工程学院", "")
        for frame in (
            "主要讲了什么", "讲了什么", "介绍了什么", "在哪里", "在哪",
            "有哪些", "有什么", "是什么", "有几个", "几个", "多少",
            "请问", "帮我", "一下",
        ):
            query = query.replace(frame, "")
        term_sizes = (2, 3, 4, 5, 6) if len(query) < 4 else (4, 5, 6)
        terms = {
            query[i : i + size]
            for size in term_sizes
            for i in range(max(0, len(query) - size + 1))
            if not query[i : i + size].isdigit() or len(query[i : i + size]) >= 4
        }
        # 常见业务称谓不是字面同义词：本科招生章程通常以“普通高考招生章程”发布。
        if "本科" in query:
            terms.update({"普通高考", "本科招生"})
        hits: list[dict[str, Any]] = []
        for chunk_id, doc, meta in zip(ids, docs, metas):
            meta = meta or {}
            title = str(meta.get("title") or "").lower()
            body = f"{title} {doc or ''}".lower()
            score = 0.0
            if query and query in title:
                score += 4.0
            if query and query in body:
                score += 1.5
            score += sum(0.12 + len(term) * 0.18 for term in terms if term in title)
            score += sum(0.03 + len(term) * 0.02 for term in terms if term in body)
            if "章程" in query:
                if "招生章程" in title:
                    score += 15.0
                elif "简章" in title:
                    score -= 10.0
            if (
                "校区" in query
                and not any(term in query for term in ("电话", "网络", "报障", "联系", "天气", "路线"))
                and any(
                marker in title for marker in ("学校概况", "学校简介", "校园概况")
                )
            ):
                score += 8.0
            if "本科" in query and any(term in title for term in ("研究生", "硕士")):
                score -= 8.0
            if score <= 0:
                continue
            hits.append(
                {
                    "snippet": doc or "",
                    "title": meta.get("title", ""),
                    "department": meta.get("department"),
                    "url": meta.get("source_url", ""),
                    "publish_date": meta.get("publish_date"),
                    # lexical hits carry an explicit bonus so an exact named
                    # document can outrank a dense hit whose score is tied at 1.0.
                    "score": 1.0 + score,
                    "metadata": meta,
                    "chunk_id": chunk_id,
                    "chunk_index": _chunk_index_from_id(chunk_id),
                }
            )
        hits.sort(key=lambda hit: (-hit["score"], hit.get("chunk_id") or ""))
        return hits[: top_k or settings.rag_top_k]

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
