from backend.rag.contracts import Evidence
from backend.rag.evidence_fusion import EvidenceFusion
from backend.rag.retriever import RAGRetriever


def test_rrf_prefers_evidence_supported_by_multiple_rankers_even_with_lower_raw_score():
    fusion = EvidenceFusion(max_items=2)
    supported = Evidence(
        evidence_id="supported",
        kind="rag",
        retriever="campus_rag",
        score=0.2,
        dense_rank=1,
        lexical_rank=1,
    )
    dense_only = Evidence(
        evidence_id="dense-only",
        kind="rag",
        retriever="campus_rag",
        score=0.99,
        dense_rank=2,
    )

    bundle = fusion.fuse(
        "招生章程",
        [dense_only, supported],
        retrievers=["campus_rag"],
    )

    assert [item.evidence_id for item in bundle.evidences] == ["supported", "dense-only"]
    assert bundle.evidences[0].fusion_score > bundle.evidences[1].fusion_score


def test_rrf_deduplicates_chunks_by_document_and_parent():
    fusion = EvidenceFusion(max_items=5)
    first = Evidence(
        evidence_id="doc-a-child-1",
        kind="rag",
        retriever="campus_rag",
        score=0.3,
        dense_rank=1,
        doc_id="doc-a",
        chunk_id="child-1",
        metadata={"parent_id": "parent-1"},
    )
    second = Evidence(
        evidence_id="doc-a-child-2",
        kind="rag",
        retriever="campus_rag",
        score=0.9,
        lexical_rank=1,
        doc_id="doc-a",
        chunk_id="child-2",
        metadata={"parent_id": "parent-1"},
    )

    bundle = fusion.fuse("招生章程", [first, second], retrievers=["campus_rag"])

    assert len(bundle.evidences) == 1
    assert bundle.evidences[0].dense_rank == 1
    assert bundle.evidences[0].lexical_rank == 1


def test_tool_rank_is_an_independent_rrf_input():
    evidence = Evidence.from_tool_item(
        {"title": "招生办", "rank": 2, "score": 100.0},
        tool="contact_search",
    )

    assert evidence.tool_rank == 2


def test_retriever_merge_keeps_dense_and_lexical_ranks():
    merged = RAGRetriever._merge_hits(
        [
            {
                "chunk_id": "right",
                "score": 0.2,
                "dense_rank": 1,
                "retrieval_source": "dense",
            },
            {
                "chunk_id": "other",
                "score": 0.99,
                "dense_rank": 2,
                "retrieval_source": "dense",
            },
        ],
        [
            {
                "chunk_id": "right",
                "score": 0.1,
                "lexical_rank": 1,
                "retrieval_source": "lexical",
            }
        ],
    )

    ordered = RAGRetriever._sort_and_dedupe(merged)

    assert ordered[0]["chunk_id"] == "right"
    assert ordered[0]["dense_rank"] == 1
    assert ordered[0]["lexical_rank"] == 1
