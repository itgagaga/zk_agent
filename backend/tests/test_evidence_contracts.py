from backend.rag.contracts import Evidence, EvidenceBundle


def test_tool_item_has_stable_identity_and_preserves_citation_fields():
    evidence = Evidence.from_tool_item(
        {
            "title": "缓考申请表",
            "file_url": "/files/late.pdf",
            "source_page_url": "https://example.edu/downloads",
            "department": "教务处",
            "snippet": "下载申请表",
        },
        tool="download_search",
    )

    assert evidence.evidence_id == "download_search:/files/late.pdf"
    assert evidence.kind == "tool"
    assert evidence.to_source_dict()["url"] == "/files/late.pdf"
    assert evidence.to_source_dict()["score"] == 0.0


def test_rag_hit_uses_doc_and_chunk_identity():
    evidence = Evidence.from_rag_hit(
        {
            "chunk_id": "doc-a_3",
            "snippet": "申请条件",
            "score": 0.82,
            "metadata": {"doc_id": "doc-a", "user_id": 7, "title": "缓考申请"},
        }
    )

    assert evidence.evidence_id == "doc-a_3"
    assert evidence.doc_id == "doc-a"
    assert evidence.kind == "document"


def test_bundle_reports_independent_sources_without_dropping_diagnostics():
    bundle = EvidenceBundle(
        query="申请条件",
        evidences=[
            Evidence.from_tool_item({"title": "申请表"}, tool="download_search"),
            Evidence.from_rag_hit({"chunk_id": "doc-a_1", "snippet": "条件"}),
        ],
        retrievers=["download_search", "campus_rag"],
        independent_source_count=2,
        coverage=1.0,
        diagnostics={"raw_candidates": 9},
    )

    assert bundle.independent_source_count == 2
    assert bundle.diagnostics["raw_candidates"] == 9
    assert len(bundle.sources()) == 2
