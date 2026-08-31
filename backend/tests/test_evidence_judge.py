from backend.rag.contracts import Evidence, EvidenceBundle, SubQuestion
from backend.rag.evidence_gate import EvidenceGate


def _rag(chunk_id: str, title: str, snippet: str, *, doc_id: str | None = None, parent_id: str | None = None):
    metadata = {}
    if doc_id:
        metadata["doc_id"] = doc_id
    if parent_id:
        metadata["parent_id"] = parent_id
    return Evidence.from_rag_hit(
        {"chunk_id": chunk_id, "title": title, "snippet": snippet, "score": 0.8, "metadata": metadata}
    )


def test_generic_campus_description_does_not_support_lost_campus_card():
    bundle = EvidenceBundle(
        query="校园卡丢了怎么办",
        evidences=[_rag("campus-1", "校园概况", "学校设有海珠校区和白云校区")],
    )

    assessment = EvidenceGate().assess(bundle)

    assert assessment.status == "unsupported"


def test_master_charter_does_not_support_undergraduate_charter_question():
    bundle = EvidenceBundle(
        query="2026年本科招生章程主要讲了什么",
        evidences=[_rag("master-1", "2026年硕士研究生招生章程", "研究生报名与考试安排")],
    )

    assessment = EvidenceGate().assess(bundle)

    assert assessment.status != "supported"
    assert assessment.conflicts


def test_white_cloud_evidence_does_not_fully_support_haizhu_followup():
    bundle = EvidenceBundle(
        query="那海珠校区呢",
        evidences=[_rag("white-1", "白云校区网络服务", "白云校区网络报障电话")],
    )

    assessment = EvidenceGate().assess(bundle)

    assert assessment.status != "supported"
    assert assessment.missing_information


def test_overall_assessment_is_partial_when_only_two_of_three_subquestions_have_evidence():
    subquestions = [
        SubQuestion(id="q1", query="校园卡补办材料", retrievers=["campus_rag"]),
        SubQuestion(id="q2", query="校园卡服务地点", retrievers=["campus_rag"]),
        SubQuestion(id="q3", query="校园卡联系电话", retrievers=["contact_search"]),
    ]
    evidences = [
        _rag("material", "校园卡补办材料", "需要学生证和照片"),
        _rag("place", "校园卡服务地点", "服务中心位于海珠校区"),
    ]
    evidences[0].metadata["subquestion_id"] = "q1"
    evidences[1].metadata["subquestion_id"] = "q2"
    bundle = EvidenceBundle(query="校园卡材料、地点、电话", evidences=evidences, subquestions=subquestions)

    assessment = EvidenceGate().assess(bundle)

    assert assessment.status == "partial"
    assert assessment.subquestions[-1].status == "unsupported"


def test_five_chunks_from_one_document_count_as_one_independent_source():
    evidences = [
        _rag(f"chunk-{index}", "培养方案", f"课程片段 {index}", doc_id="plan-1", parent_id="parent-1")
        for index in range(5)
    ]
    bundle = EvidenceBundle(query="培养方案课程安排", evidences=evidences)

    assessment = EvidenceGate().assess(bundle)

    assert assessment.subquestions[0].independent_source_count == 1


def test_low_rrf_score_is_rejected_even_when_raw_score_is_high():
    evidence = _rag("weak", "本科招生章程", "招生计划和录取规则")
    evidence.fusion_score = 0.001
    bundle = EvidenceBundle(query="本科招生章程", evidences=[evidence])

    assessment = EvidenceGate().assess(bundle)

    assert assessment.status == "unsupported"


def test_structured_judge_output_is_validated_and_applied():
    async def fake_judge(payload):
        assert payload["evidence"][0]["evidence_id"] == "campus-1"
        return {
            "status": "partial",
            "coverage": 0.5,
            "missing_information": ["联系电话"],
            "reason": "仅覆盖部分问题",
        }

    evidence = _rag("campus-1", "校园卡服务", "校园卡办理地点")
    bundle = EvidenceBundle(query="校园卡办理地点和联系电话", evidences=[evidence])

    import asyncio

    assessment = asyncio.run(EvidenceGate(judge=fake_judge).assess_async(bundle))

    assert assessment.status == "partial"
    assert assessment.missing_information == ["联系电话"]
