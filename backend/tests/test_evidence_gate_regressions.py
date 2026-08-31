"""Task 0：记录旧 Evidence Gate 的已知误判，供 Task 5 替换。"""
from __future__ import annotations

from backend.rag.contracts import Evidence, EvidenceBundle
from backend.rag.evidence_gate import EvidenceGate


def _bundle(query: str, *items: tuple[str, str]) -> EvidenceBundle:
    return EvidenceBundle(
        query=query,
        evidences=[
            Evidence.from_rag_hit({"chunk_id": key, "title": title, "snippet": "校园综合服务介绍", "score": 0.9})
            for key, title in items
        ],
        retrievers=["campus_rag"],
    )


def test_generic_campus_evidence_must_not_support_lost_campus_card():
    assessment = EvidenceGate().assess(_bundle("校园卡丢了怎么办", ("campus-1", "校园概况")))
    assert assessment.status != "supported"


def test_white_cloud_evidence_must_not_support_haizhu_followup():
    assessment = EvidenceGate().assess(_bundle(
        "白云校区网络报障电话是多少；当前追问：那海珠校区呢",
        ("white-1", "白云校区网络服务与联系方式"),
    ))
    assert assessment.status != "supported"


def test_two_of_three_subquestions_must_not_be_reported_as_fully_supported():
    assessment = EvidenceGate().assess(_bundle(
        "校园卡丢了，材料、地点、电话分别是什么",
        ("card-1", "校园卡补办材料"),
        ("card-2", "校园卡服务地点"),
    ))
    assert assessment.status != "supported"
