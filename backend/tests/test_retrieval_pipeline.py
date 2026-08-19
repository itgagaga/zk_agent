import asyncio

from backend.rag.contracts import Evidence
from backend.rag.evidence_fusion import EvidenceFusion
from backend.rag.query_planner import QueryPlanner


def test_planner_keeps_multiple_retrievers_for_download_question():
    plan = QueryPlanner().plan("缓考申请表在哪里下载？")

    assert "campus_rag" in plan.retrievers
    assert "download_search" in plan.retrievers
    assert plan.allow_fallback is True
    assert plan.subquestions[0].query


def test_planner_adds_live_retrievers_without_excluding_campus_context():
    plan = QueryPlanner().plan("从海珠校区到白云校区怎么走，明天天气如何？")

    assert {"map_route", "weather_search", "campus_rag"}.issubset(plan.retrievers)


def test_fusion_deduplicates_and_preserves_independent_source_count():
    fusion = EvidenceFusion(max_items=3)
    evidences = [
        Evidence.from_rag_hit({"chunk_id": "a", "title": "政策", "score": 0.8}),
        Evidence.from_rag_hit({"chunk_id": "a", "title": "政策", "score": 0.9}),
        Evidence.from_tool_item({"title": "缓考申请表", "file_url": "/late.pdf"}, tool="download_search"),
        Evidence.from_tool_item({"title": "网络中心", "phone": "123"}, tool="contact_search"),
    ]

    bundle = fusion.fuse("缓考申请表", evidences, retrievers=["campus_rag", "download_search", "contact_search"])

    assert len(bundle.evidences) == 3
    assert bundle.evidences[0].score >= bundle.evidences[1].score
    assert bundle.independent_source_count == 3
    assert bundle.coverage == 1.0
