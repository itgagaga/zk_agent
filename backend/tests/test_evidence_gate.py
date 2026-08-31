from backend.rag.contracts import Evidence, EvidenceBundle
from backend.rag.evidence_gate import EvidenceGate


def _bundle(query, *evidences):
    return EvidenceBundle(query=query, evidences=list(evidences), retrievers=["campus_rag"])


def test_gate_accepts_undergraduate_charter_evidence_for_semantic_title_variant():
    bundle = _bundle(
        "2026年本科招生章程主要讲了什么",
        Evidence.from_rag_hit(
            {
                "chunk_id": "zsb_bkzs_zc_2026_0",
                "title": "2026年普通高考招生章程",
                "snippet": "学校概况、招生计划、录取规则和收费标准",
                "score": 0.9,
            }
        ),
    )

    assessment = EvidenceGate().assess(bundle)

    assert assessment.status == "supported"
    assert assessment.coverage >= 0.8
    assert "章程" in assessment.matched_concepts


def test_gate_rejects_generic_year_documents_that_do_not_cover_question():
    bundle = _bundle(
        "2026年本科招生章程主要讲了什么",
        Evidence.from_rag_hit(
            {"chunk_id": "job-1", "title": "2026年招聘信息", "snippet": "招聘安排", "score": 0.9}
        ),
        Evidence.from_rag_hit(
            {"chunk_id": "master-1", "title": "2026年硕士研究生招生章程", "snippet": "研究生报名", "score": 0.8}
        ),
    )

    assessment = EvidenceGate().assess(bundle)

    assert assessment.status in {"partial", "unsupported"}
    assert "本科" in assessment.missing_concepts or "普通高考" in assessment.missing_concepts
