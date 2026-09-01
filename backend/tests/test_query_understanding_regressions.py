"""Task 0：自然表达、追问和私有文档范围的离线回归基线。"""
from __future__ import annotations

import asyncio

from analytics.evaluation import load_semantic_cases, semantic_case_metrics
from backend.rag.query_planner import QueryPlanner


async def _resolve(plan):
    return await plan


def _offline_planner() -> QueryPlanner:
    planner = QueryPlanner()
    planner._structured_llm = None
    return planner


def _plan(case, *, user_id: int | None = None, knowledge_scope: str = "auto"):
    return asyncio.run(_resolve(_offline_planner().plan(
        case.question,
        history=case.history,
        user_id=user_id,
        knowledge_scope=knowledge_scope,
        has_personal_documents=knowledge_scope != "auto",
    )))


def test_semantic_fixture_is_offline_and_covers_regression_dimensions():
    cases = load_semantic_cases()
    assert len(cases) >= 40
    assert {"weather_search", "map_route", "job_search", "news_search"}.issubset(
        {target for case in cases for target in case.expected_retrievers}
    )
    assert any(case.history for case in cases)
    assert any(case.forbidden_retrievers for case in cases)


def test_rule_fallback_handles_semantic_tool_and_negative_cases():
    cases = load_semantic_cases()
    plans = []
    for case in cases:
        user_id = 7 if case.id.startswith("private-") and case.id != "private-03" else None
        scope = "with_personal" if user_id is not None else "auto"
        plan = _plan(case, user_id=user_id, knowledge_scope=scope)
        plans.append(plan)
        predicted = set(plan.retrievers)
        assert case.expected_retrievers.issubset(predicted), case.id
        assert not (predicted & case.forbidden_retrievers), case.id
        if case.expected_subquestions is not None:
            assert len(plan.subquestions) == case.expected_subquestions, case.id

    metrics = semantic_case_metrics(cases, plans)
    assert metrics["retriever_selection_micro_f1"] >= 0.85


def test_followup_query_preserves_previous_network_and_new_campus_entities():
    plan = asyncio.run(_resolve(_offline_planner().plan(
        "那海珠校区呢",
        history=[{"role": "user", "content": "白云校区网络报障电话是多少？"}],
    )))

    assert plan.used_history is True
    assert "海珠校区" in plan.standalone_query
    assert "网络报障" in plan.standalone_query
    assert "contact_search" in plan.retrievers
    assert plan.subquestions[0].entities.get("campus") == "海珠校区"


def test_private_documents_require_explicit_intent_and_user_scope():
    planner = _offline_planner()
    weather = asyncio.run(_resolve(planner.plan("今天要不要带伞", user_id=7)))
    private = asyncio.run(_resolve(planner.plan(
        "我的培养方案要求多少学分",
        user_id=7,
        knowledge_scope="with_personal",
        has_personal_documents=True,
    )))
    guest_private = asyncio.run(_resolve(planner.plan("我的培养方案要求多少学分")))

    assert "user_docs" not in weather.retrievers
    assert "user_docs" in private.retrievers
    assert "major_search" in private.retrievers
    assert "user_docs" not in guest_private.retrievers
