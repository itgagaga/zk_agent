"""Task 5：结合个人资料时的证据平衡与最终引用边界。"""
from __future__ import annotations

import asyncio

from backend.rag.contracts import Evidence, EvidenceBundle, RetrievalPlan, SubQuestion
from backend.rag.evidence_gate import EvidenceGate
from backend.rag.retrieval_manager import RetrievalManager


def _rag(
    chunk_id: str,
    title: str,
    snippet: str,
    *,
    score: float = 0.9,
    user_id: int | None = None,
) -> Evidence:
    metadata = {"doc_id": chunk_id}
    if user_id is not None:
        metadata["user_id"] = user_id
    return Evidence.from_rag_hit({
        "chunk_id": chunk_id,
        "title": title,
        "snippet": snippet,
        "score": score,
        "metadata": metadata,
    }, retriever="user_docs" if user_id is not None else "campus_rag")


def test_weather_drops_irrelevant_personal_curriculum_from_final_evidence():
    weather = Evidence.from_tool_item({
        "title": "广州今日天气",
        "snippet": "今天晴，降雨概率低，不需要带伞。",
        "score": 0.9,
    }, tool="weather_search")
    personal = _rag(
        "personal-plan",
        "我的信息与计算科学培养方案",
        "大一课程包括高等数学和程序设计。",
        user_id=7,
    )
    bundle = EvidenceBundle(
        query="今天天气怎么样，要不要带伞",
        evidences=[weather, personal],
        retrievers=["weather_search", "user_docs"],
        subquestions=[SubQuestion(
            id="q1",
            query="今天天气怎么样，要不要带伞",
            retrievers=["weather_search", "user_docs"],
        )],
    )

    gate = EvidenceGate()
    assessment = gate.assess(bundle)
    selected = gate.filter_for_answer(bundle, assessment)

    assert assessment.status == "supported"
    assert [item.evidence_id for item in selected] == [weather.evidence_id]


def test_curriculum_keeps_direct_public_and_personal_evidence():
    public = _rag(
        "public-plan",
        "信息与计算科学专业培养方案",
        "大一课程安排包括高等数学、程序设计和大学英语。",
    )
    personal = _rag(
        "personal-plan",
        "我的培养方案",
        "大一课程安排包括高等数学和程序设计。",
        user_id=7,
    )
    bundle = EvidenceBundle(
        query="信息与计算科学专业大一课程安排",
        evidences=[public, personal],
        retrievers=["campus_rag", "user_docs"],
    )

    gate = EvidenceGate()
    assessment = gate.assess(bundle)
    selected = gate.filter_for_answer(bundle, assessment)

    assert assessment.status == "supported"
    assert {item.evidence_id for item in selected} == {public.evidence_id, personal.evidence_id}


def test_different_document_years_are_partial_and_report_conflict():
    bundle = EvidenceBundle(
        query="2025年本科培养方案",
        evidences=[
            _rag("public-2024", "2024年本科培养方案", "本科课程安排和毕业要求。"),
            _rag("personal-2025", "我的2025年培养方案", "2025年课程安排。", user_id=7),
        ],
        retrievers=["campus_rag", "user_docs"],
    )

    assessment = EvidenceGate().assess(bundle)

    assert assessment.status == "partial"
    assert assessment.conflicts
    assert any("年份" in conflict for conflict in assessment.conflicts)


def test_irrelevant_personal_chunks_cannot_suppress_direct_public_evidence():
    public = _rag(
        "public-card",
        "校园卡服务指南",
        "校园卡挂失后可以到服务中心补办。",
        score=0.4,
    )
    personal_chunks = [
        _rag(
            f"personal-{index}",
            "我的培养方案",
            "大一课程与学分要求。",
            score=0.99,
            user_id=7,
        )
        for index in range(3)
    ]
    bundle = EvidenceBundle(
        query="校园卡丢了怎么办",
        evidences=[public, *personal_chunks],
        retrievers=["campus_rag", "user_docs"],
    )

    gate = EvidenceGate()
    assessment = gate.assess(bundle)
    selected = gate.filter_for_answer(bundle, assessment)

    assert assessment.status == "supported"
    assert [item.evidence_id for item in selected] == [public.evidence_id]


def test_enhanced_personal_evidence_is_not_removed_by_another_subquestion():
    public = _rag(
        "public-job",
        "校园招聘会信息",
        "招聘会安排和报名方式。",
        user_id=None,
    )
    personal = _rag(
        "personal-plan",
        "我的信息与计算科学培养方案",
        "大四阶段应完成专业课程、毕业实习和毕业设计。",
        user_id=7,
    )
    public.metadata["subquestion_id"] = "q1"
    personal.metadata["subquestion_id"] = "q2"
    bundle = EvidenceBundle(
        query="信计大四学生的学业与就业建议",
        evidences=[public, personal],
        retrievers=["campus_rag", "user_docs"],
        subquestions=[
            SubQuestion(
                id="q1",
                query="校园招聘会有哪些信息",
                retrievers=["campus_rag", "user_docs"],
            ),
            SubQuestion(
                id="q2",
                query="信计大四学生的学业与就业建议",
                retrievers=["campus_rag", "user_docs"],
            ),
        ],
        diagnostics={"knowledge_scope": "with_personal"},
    )

    gate = EvidenceGate()
    assessment = gate.assess(bundle)
    selected = gate.filter_for_answer(bundle, assessment)

    assert assessment.status == "partial"
    assert {item.evidence_id for item in selected} == {
        public.evidence_id,
        personal.evidence_id,
    }


def test_personal_only_without_hit_does_not_fallback_to_public_retrieval():
    class NoHitRetriever:
        def __init__(self):
            self.calls = []

        async def search(self, query, top_k=None, where=None):
            self.calls.append("campus_rag")
            raise AssertionError("personal_only 不应调用公开校园库")

        async def search_user_documents(self, query, *, user_id, top_k=None, where=None):
            self.calls.append(("user_docs", user_id))
            return []

    retriever = NoHitRetriever()
    plan = RetrievalPlan(
        original_query="个人课程安排",
        standalone_query="个人课程安排",
        subquestions=[SubQuestion(
            id="q1",
            query="个人课程安排",
            retrievers=["campus_rag"],
        )],
        knowledge_scope="personal_only",
        base_retrievers=["campus_rag"],
        retrievers=["campus_rag"],
    )

    bundle = asyncio.run(RetrievalManager(retriever=retriever, tools={}).retrieve(plan, user_id=7))

    assert retriever.calls == [("user_docs", 7)]
    assert bundle.evidences == []
