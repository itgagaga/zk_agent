"""Task 3：中文 BM25 词法召回回归测试。"""
from __future__ import annotations

from backend.rag.lexical_index import LexicalDocument, LexicalIndex, tokenize
from backend.rag.vector_store import VectorStore


def test_tokenizer_uses_domain_terms_instead_of_character_windows():
    tokens = tokenize("广州南站到白云校区的网络报障电话")

    assert "白云校区" in tokens
    assert "网络报障" in tokens
    assert "云校" not in tokens


def test_bm25_prefers_title_and_structured_fields_for_named_document():
    index = LexicalIndex([
        LexicalDocument(
            "wrong",
            "普通高考招生政策的背景说明。",
            {"title": "2026年招生政策说明", "department": "学生工作部"},
        ),
        LexicalDocument(
            "right",
            "招生计划、录取规则和收费标准。",
            {"title": "2026年普通高考招生章程", "document_type": "招生章程"},
        ),
    ])

    hits = index.search("2026年本科招生章程", top_k=2)

    assert hits[0]["chunk_id"] == "right"
    assert hits[0]["lexical_rank"] == 1
    assert hits[0]["bm25_score"] > 0


def test_common_words_alone_do_not_return_arbitrary_documents():
    index = LexicalIndex([
        LexicalDocument("a", "下载速度与浏览器缓存说明", {"title": "下载速度说明"}),
        LexicalDocument("b", "学校历史和校园简介", {"title": "学校概况"}),
    ])

    assert index.search("下载", top_k=5) == []
    assert index.search("学校", top_k=5) == []


def test_index_upsert_delete_rebuilds_collection_state():
    index = LexicalIndex([LexicalDocument("a", "海珠校区地址", {"title": "海珠校区"})])
    index.upsert([LexicalDocument("b", "白云校区地址", {"title": "白云校区"})])

    assert index.search("白云校区", top_k=1)[0]["chunk_id"] == "b"

    index.delete(["b"])

    assert all(hit["chunk_id"] != "b" for hit in index.search("白云校区", top_k=5))


def test_vector_store_invalidates_only_touched_collection_lexical_index():
    store = VectorStore()
    store._lexical_indexes["zhku"] = LexicalIndex()
    store._lexical_indexes["document"] = LexicalIndex()

    store.invalidate_lexical_index("document")

    assert store._lexical_indexes["document"] is None
    assert store._lexical_indexes["zhku"] is not None
