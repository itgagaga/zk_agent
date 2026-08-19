import asyncio

from backend.rag.retriever import RAGRetriever
from backend.rag.vector_store import VectorStore


class FakeStore:
    def __init__(self, hits):
        self.hits = hits
        self.query_top_k = None
        self.query_where = None
        self.parent_calls = []
        self.doc_calls = []
        self.count_calls = []

    def query(self, *, text, top_k, where, collection):
        self.query_top_k = top_k
        self.query_where = where
        return list(self.hits)

    def keyword_search(self, *, text, top_k, where, collection):
        return []

    def get_chunks_by_parent_id(self, parent_id, doc_id=None, user_id=None, collection="zhku"):
        self.parent_calls.append((parent_id, doc_id, user_id, collection))
        return []

    def count_documents(self, where=None, collection="document"):
        self.count_calls.append((where, collection))
        return 99

    def get_chunks_by_doc_id(self, doc_id, user_id=None, collection="user_docs"):
        self.doc_calls.append((doc_id, user_id, collection))
        return []


def _retriever(monkeypatch, store):
    monkeypatch.setattr("backend.rag.retriever.get_vector_store", lambda: store)
    retriever = RAGRetriever()
    retriever.score_threshold = 0.1
    return retriever


def test_search_overfetches_before_threshold_and_refills_top_k(monkeypatch):
    store = FakeStore(
        [
            {"chunk_id": "low-1", "score": 0.01, "snippet": "noise", "metadata": {}},
            {"chunk_id": "low-2", "score": 0.02, "snippet": "noise", "metadata": {}},
            {"chunk_id": "right", "score": 0.88, "snippet": "缓考申请表", "metadata": {}},
            {"chunk_id": "also-right", "score": 0.72, "snippet": "申请条件", "metadata": {}},
        ]
    )
    retriever = _retriever(monkeypatch, store)

    hits = asyncio.run(retriever.search("缓考申请表", top_k=2))

    assert store.query_top_k >= 8
    assert [hit["chunk_id"] for hit in hits] == ["right", "also-right"]


def test_user_document_followup_fetches_keep_user_scope(monkeypatch):
    store = FakeStore(
        [{
            "chunk_id": "doc-a_0",
            "score": 0.8,
            "snippet": "private",
            "metadata": {"doc_id": "doc-a", "user_id": 7},
        }]
    )
    retriever = _retriever(monkeypatch, store)

    asyncio.run(retriever.search_documents("private", top_k=2, user_id=7))

    assert store.parent_calls == []
    assert store.query_where == {"user_id": 7}
    assert store.count_calls[0][0] == {"doc_id": "doc-a", "user_id": 7}


def test_keyword_search_prefers_admission_charter_over_other_2026_documents():
    class Collection:
        def get(self, **kwargs):
            return {
                "ids": ["job-2026", "master-2026", "undergrad-charter"],
                "documents": [
                    "2026年招聘信息",
                    "2026年硕士研究生招生章程",
                    "2026年普通高考招生章程 学校概况 招生计划 录取规则 学费标准",
                ],
                "metadatas": [
                    {"title": "2026年招聘信息"},
                    {"title": "2026年硕士研究生招生章程"},
                    {"title": "2026年普通高考招生章程"},
                ],
            }

    store = VectorStore()
    store._target = lambda collection: Collection()

    hits = store.keyword_search(text="2026年本科招生章程主要讲了什么", top_k=1)
    assert hits[0]["chunk_id"] == "undergrad-charter"


def test_keyword_search_prefers_charter_title_over_brochure_title():
    class Collection:
        def get(self, **kwargs):
            return {
                "ids": ["brochure", "charter"],
                "documents": [
                    "2026年本科招生简章。招生章程已发布，详见官网。",
                    "2026年普通高考招生章程。招生计划、录取规则、收费标准。",
                ],
                "metadatas": [
                    {"title": "仲恺农业工程学院2026年本科招生简章"},
                    {"title": "2026年普通高考招生章程"},
                ],
            }

    store = VectorStore()
    store._target = lambda collection: Collection()

    hits = store.keyword_search(text="2026年本科招生章程主要讲了什么", top_k=1)
    assert hits[0]["chunk_id"] == "charter"


def test_keyword_search_removes_common_institution_name_and_boosts_campus_profile():
    class Collection:
        def get(self, **kwargs):
            return {
                "ids": ["finance", "profile"],
                "documents": [
                    "仲恺农业工程学院财务部服务指南和报账信息。",
                    "学校概况：学校地址位于海珠校区和白云校区。",
                ],
                "metadatas": [
                    {"title": "仲恺农业工程学院财务部服务指南"},
                    {"title": "仲恺农业工程学院学校概况"},
                ],
            }

    store = VectorStore()
    store._target = lambda collection: Collection()

    hits = store.keyword_search(text="仲恺农业工程学院有几个校区？", top_k=2)
    assert hits[0]["chunk_id"] == "profile"
