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


def test_hybrid_planner_removes_private_target_for_guest_even_if_llm_requests_it():
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
    assert "shared_docs" not in plan.retrievers
    assert "登录" in plan.planner_reason
