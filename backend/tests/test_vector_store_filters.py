from backend.rag.vector_store import VectorStore, combine_where, normalize_where


class StrictCollection:
    """模拟 Chroma 对根级 where 的严格校验。"""

    def __init__(self):
        self.where_calls = []

    def _validate(self, where):
        self.where_calls.append(where)
        if where and len(where) != 1:
            raise ValueError("Expected where to have exactly one operator")

    def get(self, *, where=None, include=None):
        self._validate(where)
        return {
            "ids": ["doc_0"],
            "documents": ["培养方案片段"],
            "metadatas": [{
                "doc_id": "doc-a",
                "user_id": 7,
                "title": "培养方案",
                "chunk_index": 0,
            }],
        }

    def delete(self, **kwargs):
        self._validate(kwargs.get("where"))


def test_plain_multi_field_where_is_normalized_to_and():
    assert normalize_where({"doc_id": "doc-a", "user_id": 7}) == {
        "$and": [{"doc_id": "doc-a"}, {"user_id": 7}]
    }
    assert combine_where({"doc_id": "doc-a"}, {"user_id": 7}) == {
        "$and": [{"doc_id": "doc-a"}, {"user_id": 7}]
    }


def test_vector_store_normalizes_count_and_document_fetch_filters():
    collection = StrictCollection()
    store = VectorStore()
    store._target = lambda collection_name: collection

    assert store.count_documents(
        where={"doc_id": "doc-a", "user_id": 7}, collection="user_docs"
    ) == 1
    hits = store.get_chunks_by_doc_id("doc-a", user_id=7, collection="user_docs")

    assert len(hits) == 1
    assert all(where is None or len(where) == 1 for where in collection.where_calls)
    assert {"$and": [{"doc_id": "doc-a"}, {"user_id": 7}]} in collection.where_calls


def test_delete_normalizes_multi_field_scope_before_calling_chroma():
    collection = StrictCollection()
    store = VectorStore()
    store._target = lambda collection_name: collection

    store.delete_documents(
        where={"doc_id": "doc-a", "user_id": 7}, collection="user_docs"
    )

    assert collection.where_calls == [{"$and": [{"doc_id": "doc-a"}, {"user_id": 7}]}]
