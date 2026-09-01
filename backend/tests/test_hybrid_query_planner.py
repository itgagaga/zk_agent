"""Task 1：Hybrid Planner 的结构化输出和服务端约束。"""
from __future__ import annotations

import asyncio

from backend.rag.query_planner import QueryPlanner


class FakeStructuredLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        return self.payload


async def _resolve(planner: QueryPlanner, question: str, **kwargs):
    return await planner.plan(question, **kwargs)


def test_hybrid_planner_calls_structured_llm_once_and_preserves_plan_fields():
    planner = QueryPlanner()
    fake = FakeStructuredLLM({
        "standalone_query": "海珠校区网络报障电话",
        "subquestions": [{
            "id": "ignored-by-server",
            "query": "海珠校区网络报障电话",
            "intent": "contact",
            "retrievers": ["contact_search", "service_link_search"],
            "entities": {"campus": "海珠校区"},
        }],
        "retrievers": ["contact_search", "service_link_search"],
        "planner_reason": "根据校区和报障意图选择联系方式工具",
    })
    planner._structured_llm = fake

    plan = asyncio.run(_resolve(planner, "那海珠校区呢", history=[
        {"role": "user", "content": "白云校区网络报障电话是多少"},
    ]))

    assert fake.calls == 1
    assert plan.planner_source == "llm"
    assert plan.standalone_query == "海珠校区网络报障电话"
    assert plan.subquestions[0].id == "q1"
    assert plan.subquestions[0].entities["campus"] == "海珠校区"


def test_auto_scope_removes_private_target_but_keeps_public_target():
    planner = QueryPlanner()
    planner._structured_llm = FakeStructuredLLM({
        "standalone_query": "我的培养方案学分要求",
        "subquestions": [{
            "id": "q1",
            "query": "我的培养方案学分要求",
            "intent": "private_document",
            "retrievers": ["user_docs", "shared_docs"],
        }],
    })

    plan = asyncio.run(_resolve(planner, "我的培养方案要求多少学分"))

    assert "user_docs" not in plan.retrievers
    assert "shared_docs" in plan.retrievers


def test_scope_is_server_authoritative_and_auto_removes_llm_private_target():
    planner = QueryPlanner()
    planner._structured_llm = FakeStructuredLLM({
        "standalone_query": "信计大一课程安排",
        "subquestions": [{
            "id": "q1",
            "query": "信计大一课程安排",
            "intent": "major",
            "retrievers": ["campus_rag", "user_docs"],
        }],
    })

    plan = asyncio.run(_resolve(
        planner,
        "信计大一要学什么",
        user_id=7,
        knowledge_scope="auto",
        has_personal_documents=True,
    ))

    assert "user_docs" not in plan.retrievers
    assert all("user_docs" not in subquestion.retrievers for subquestion in plan.subquestions)


def test_auto_scope_falls_back_to_public_plan_when_llm_only_returns_private_target():
    planner = QueryPlanner()
    planner._structured_llm = FakeStructuredLLM({
        "standalone_query": "我的培养方案课程安排",
        "subquestions": [{
            "id": "q1",
            "query": "我的培养方案课程安排",
            "intent": "private_document",
            "retrievers": ["user_docs"],
        }],
    })

    plan = asyncio.run(_resolve(
        planner,
        "我的培养方案课程安排",
        user_id=7,
        knowledge_scope="auto",
        has_personal_documents=True,
    ))

    assert "user_docs" not in plan.retrievers
    assert plan.retrievers


def test_with_personal_adds_user_docs_when_llm_omits_it():
    planner = QueryPlanner()
    planner._structured_llm = FakeStructuredLLM({
        "standalone_query": "信计大一课程安排",
        "subquestions": [{
            "id": "q1",
            "query": "信计大一课程安排",
            "intent": "major",
            "retrievers": ["campus_rag"],
        }],
    })

    plan = asyncio.run(_resolve(
        planner,
        "信计大一要学什么",
        user_id=7,
        knowledge_scope="with_personal",
        has_personal_documents=True,
    ))

    assert "campus_rag" in plan.retrievers
    assert "user_docs" in plan.retrievers


def test_curriculum_question_does_not_accept_llm_academic_search_misroute():
    planner = QueryPlanner()
    planner._structured_llm = FakeStructuredLLM({
        "standalone_query": "仲恺农业工程学院信息与计算科学专业大一课程",
        "subquestions": [{
            "id": "q1",
            "query": "仲恺农业工程学院信息与计算科学专业大一课程",
            "intent": "major",
            "retrievers": ["academic_search", "campus_rag"],
        }],
    })

    plan = asyncio.run(_resolve(planner, "信计大一要学什么"))

    assert "academic_search" not in plan.retrievers


def test_rule_planner_splits_broad_major_study_advice_into_actionable_subquestions():
    planner = QueryPlanner()
    planner._structured_llm = None

    plan = asyncio.run(_resolve(planner, "我是信计大一新生，你有什么学习建议"))

    assert [subquestion.intent for subquestion in plan.subquestions] == [
        "curriculum", "practice", "advice",
    ]
    assert all("user_docs" not in subquestion.retrievers for subquestion in plan.subquestions)
    assert all("课程" in subquestion.query or "实践" in subquestion.query or "规划" in subquestion.query for subquestion in plan.subquestions)
