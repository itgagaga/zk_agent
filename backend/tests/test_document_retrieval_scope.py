"""Task 2：共享文档与用户私有文档必须显式分流。"""
from __future__ import annotations

import asyncio

from backend.config import settings
from backend.rag.contracts import RetrievalPlan, SubQuestion
from backend.rag.retrieval_manager import RetrievalManager


class TrackingRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int | None]] = []

    async def search(self, query, top_k=None, where=None):
        self.calls.append(("campus_rag", query, None))
        return []

    async def search_shared_documents(self, query, top_k=None, where=None):
        self.calls.append(("shared_docs", query, None))
        return [{"chunk_id": "shared-1", "title": "招生章程", "snippet": "共享资料", "score": 0.8}]

    async def search_user_documents(self, query, *, user_id, top_k=None, where=None):
        self.calls.append(("user_docs", query, user_id))
        return [{
            "chunk_id": "private-1",
            "title": "我的培养方案",
            "snippet": "个人资料",
            "score": 0.8,
            "metadata": {"user_id": user_id, "doc_id": "private-doc"},
        }]


def _plan(
    *targets: str,
    scope: str = "auto",
    base_targets: list[str] | None = None,
    diagnostics: dict | None = None,
) -> RetrievalPlan:
    subquestion = SubQuestion(
        id="q1",
        query="文档问题",
        intent="document",
        retrievers=list(targets),
    )
    return RetrievalPlan(
        original_query="文档问题",
        standalone_query="文档问题",
        subquestions=[subquestion],
        retrievers=list(targets),
        knowledge_scope=scope,
        base_retrievers=base_targets or [target for target in targets if target != "user_docs"],
        diagnostics=diagnostics or {},
    )


def test_shared_docs_uses_shared_collection_without_user_scope():
    retriever = TrackingRetriever()
    bundle = asyncio.run(RetrievalManager(retriever=retriever).retrieve(_plan("shared_docs"), user_id=7))

    assert retriever.calls == [("shared_docs", "文档问题", None)]
    assert bundle.evidences[0].retriever == "shared_docs"


def test_private_docs_requires_current_user_id_and_never_falls_back_to_shared_docs():
    retriever = TrackingRetriever()
    bundle = asyncio.run(RetrievalManager(retriever=retriever).retrieve(
        _plan("user_docs", scope="with_personal"),
        user_id=42,
    ))

    assert retriever.calls == [("user_docs", "文档问题", 42)]
    assert bundle.evidences[0].metadata["user_id"] == 42


def test_login_does_not_add_private_documents_to_normal_planner_result():
    from backend.rag.query_planner import QueryPlanner

    planner = QueryPlanner()
    planner._structured_llm = None
    plan = planner.plan("今天要不要带伞", user_id=42)

    assert "user_docs" not in plan.retrievers
    assert "weather_search" in plan.retrievers


def test_with_personal_keeps_public_targets_and_adds_user_documents(monkeypatch):
    monkeypatch.setattr(settings, "rag_max_retry", 0)
    retriever = TrackingRetriever()
    plan = _plan(
        "campus_rag", "shared_docs",
        scope="with_personal",
        base_targets=["campus_rag", "shared_docs"],
    )

    asyncio.run(RetrievalManager(retriever=retriever).retrieve(plan, user_id=42))

    assert retriever.calls == [
        ("campus_rag", "文档问题", None),
        ("shared_docs", "文档问题", None),
        ("user_docs", "文档问题", 42),
    ]


def test_auto_never_executes_user_documents_from_an_untrusted_plan(monkeypatch):
    monkeypatch.setattr(settings, "rag_max_retry", 0)
    retriever = TrackingRetriever()
    plan = _plan("campus_rag", "user_docs", scope="auto")

    asyncio.run(RetrievalManager(retriever=retriever).retrieve(plan, user_id=42))

    assert retriever.calls == [("campus_rag", "文档问题", None)]


def test_personal_only_never_executes_public_targets(monkeypatch):
    monkeypatch.setattr(settings, "rag_max_retry", 0)
    retriever = TrackingRetriever()
    plan = _plan("campus_rag", "shared_docs", scope="personal_only")

    asyncio.run(RetrievalManager(retriever=retriever).retrieve(plan, user_id=42))

    assert retriever.calls == [("user_docs", "文档问题", 42)]


def test_personal_only_empty_library_does_not_create_public_or_private_tasks(monkeypatch):
    monkeypatch.setattr(settings, "rag_max_retry", 0)
    retriever = TrackingRetriever()
    plan = _plan(
        "campus_rag", "shared_docs",
        scope="personal_only",
        diagnostics={"personal_documents_empty": True},
    )

    bundle = asyncio.run(RetrievalManager(retriever=retriever).retrieve(plan, user_id=42))

    assert retriever.calls == []
    assert bundle.retrievers == []
