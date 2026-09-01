"""Task 0：个人知识库资料范围的失败测试。

这些测试先固定产品语义；Task 1/2 再补齐 API、契约和 Planner 实现。
测试只使用规则降级或假的结构化 LLM，不访问外部服务。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import chat
from backend.database.models import UserDocument
from backend.rag.contracts import RetrievalPlan
from backend.rag.query_planner import QueryPlanner


def _offline_planner() -> QueryPlanner:
    planner = QueryPlanner()
    planner._structured_llm = None
    return planner


async def _resolve(planner: QueryPlanner, question: str, **kwargs):
    return await planner.plan(question, **kwargs)


def test_chat_request_defaults_to_auto_and_accepts_all_scope_values():
    assert chat.ChatRequest(question="测试").knowledge_scope == "auto"
    for scope in ("auto", "with_personal", "personal_only"):
        assert chat.ChatRequest(question="测试", knowledge_scope=scope).knowledge_scope == scope


def test_retrieval_plan_exposes_scope_and_base_retriever_fields():
    plan = RetrievalPlan(
        original_query="测试",
        standalone_query="测试",
        base_retrievers=["campus_rag"],
        retrievers=["campus_rag"],
    )

    assert plan.knowledge_scope == "auto"
    assert plan.base_retrievers == ["campus_rag"]


def test_chat_api_rejects_unauthenticated_personal_scope():
    request = chat.ChatRequest(question="测试", knowledge_scope="with_personal")

    with pytest.raises(HTTPException) as error:
        asyncio.run(chat.chat(request, None))

    assert error.value.status_code == 401


def test_chat_api_queries_current_users_personal_document_presence(monkeypatch):
    captured: dict = {}

    class FakeController:
        async def handle(self, *args, **kwargs):
            captured.update(kwargs)
            return {"answer": "ok", "confidence": "high"}

    class FakeQuery:
        def filter(self, condition):
            return self

        def first(self):
            return object()

    class FakeDB:
        def query(self, model):
            assert model is UserDocument
            return FakeQuery()

    monkeypatch.setattr(chat, "AgentController", FakeController)
    request = chat.ChatRequest(question="测试", knowledge_scope="with_personal")
    user = SimpleNamespace(id=7, role="student")

    asyncio.run(chat.chat(request, user, FakeDB()))

    assert captured["knowledge_scope"] == "with_personal"
    assert captured["has_personal_documents"] is True


def test_auto_keeps_public_plan_even_when_logged_in_and_personal_documents_exist():
    plan = asyncio.run(_resolve(
        _offline_planner(),
        "根据我上传的培养方案，信计大一要学什么",
        user_id=7,
        knowledge_scope="auto",
        has_personal_documents=True,
    ))

    assert "user_docs" not in plan.retrievers
    assert all("user_docs" not in subquestion.retrievers for subquestion in plan.subquestions)


def test_with_personal_is_default_plan_plus_user_docs():
    planner = _offline_planner()
    base = asyncio.run(_resolve(
        planner,
        "信计大一要学什么",
        user_id=7,
        knowledge_scope="auto",
        has_personal_documents=True,
    ))
    combined = asyncio.run(_resolve(
        _offline_planner(),
        "信计大一要学什么",
        user_id=7,
        knowledge_scope="with_personal",
        has_personal_documents=True,
    ))

    assert set(base.retrievers).issubset(set(combined.retrievers))
    assert "user_docs" in combined.retrievers
    assert all("user_docs" in subquestion.retrievers for subquestion in combined.subquestions)


def test_personal_only_replaces_every_retriever_with_user_docs():
    plan = asyncio.run(_resolve(
        _offline_planner(),
        "信计大一要学什么",
        user_id=7,
        knowledge_scope="personal_only",
        has_personal_documents=True,
    ))

    assert plan.retrievers == ["user_docs"]
    assert all(subquestion.retrievers == ["user_docs"] for subquestion in plan.subquestions)


@pytest.mark.parametrize("scope", ["with_personal", "personal_only"])
def test_personal_scopes_require_an_authenticated_user(scope: str):
    with pytest.raises(PermissionError):
        asyncio.run(_resolve(
            _offline_planner(),
            "信计大一要学什么",
            user_id=None,
            knowledge_scope=scope,
            has_personal_documents=True,
        ))


def test_with_personal_empty_library_keeps_default_plan_and_marks_diagnostic():
    plan = asyncio.run(_resolve(
        _offline_planner(),
        "信计大一要学什么",
        user_id=7,
        knowledge_scope="with_personal",
        has_personal_documents=False,
    ))

    assert "user_docs" not in plan.retrievers
    assert plan.retrievers
    assert "personal_documents_empty" in getattr(plan, "diagnostics", {})


def test_personal_only_empty_library_does_not_fallback_to_public_retrievers():
    plan = asyncio.run(_resolve(
        _offline_planner(),
        "信计大一要学什么",
        user_id=7,
        knowledge_scope="personal_only",
        has_personal_documents=False,
    ))

    assert plan.retrievers == []
    assert all(not subquestion.retrievers for subquestion in plan.subquestions)
    assert "personal_documents_empty" in getattr(plan, "diagnostics", {})


def test_curriculum_question_does_not_select_academic_search_in_rule_fallback():
    plan = asyncio.run(_resolve(
        _offline_planner(),
        "信计大一要学什么",
        knowledge_scope="auto",
    ))

    assert "academic_search" not in plan.retrievers
