import asyncio
import json

from backend.agents.controller import AgentController
from backend.rag.contracts import EvidenceBundle, RetrievalPlan, SubQuestion
from backend.rag.retrieval_manager import RetrievalManager


class ScopeRetriever:
    async def search(self, query, top_k=None, where=None):
        return [{"chunk_id": "public-1", "title": "公开资料", "snippet": "公开说明", "score": 0.8}]

    async def search_user_documents(self, query, *, user_id, top_k=None, where=None):
        return [{
            "chunk_id": "private-1",
            "title": "个人培养方案",
            "snippet": "课程安排和个人说明",
            "score": 0.8,
            "metadata": {"user_id": user_id},
        }]


def _plan(scope="with_personal"):
    return RetrievalPlan(
        original_query="课程安排",
        standalone_query="课程安排",
        subquestions=[SubQuestion(
            id="q1",
            query="课程安排",
            intent="curriculum",
            retrievers=["campus_rag", "user_docs"],
        )],
        knowledge_scope=scope,
        base_retrievers=["campus_rag"],
        retrievers=["campus_rag", "user_docs"],
    )


def test_retrieval_summary_reports_scope_and_actual_private_usage(monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "rag_max_retry", 0)
    manager = RetrievalManager(retriever=ScopeRetriever())

    bundle = asyncio.run(manager.retrieve(_plan(), user_id=9))
    summary = manager.to_legacy(bundle)["retrieval_summary"]

    assert summary["knowledge_scope"] == "with_personal"
    assert summary["base_retrievers"] == ["campus_rag"]
    assert summary["effective_retrievers"] == ["campus_rag", "user_docs"]
    assert summary["personal_documents_requested"] is True
    assert summary["personal_documents_available"] is True
    assert summary["personal_documents_used"] is True


def test_personal_only_without_hits_reports_available_but_unused(monkeypatch):
    from backend.config import settings

    class EmptyPersonalRetriever(ScopeRetriever):
        async def search_user_documents(self, query, *, user_id, top_k=None, where=None):
            return []

    monkeypatch.setattr(settings, "rag_max_retry", 0)
    manager = RetrievalManager(retriever=EmptyPersonalRetriever())
    plan = _plan("personal_only").model_copy(update={
        "retrievers": ["user_docs"],
        "subquestions": [SubQuestion(
            id="q1", query="课程安排", intent="curriculum", retrievers=["user_docs"]
        )],
    })

    bundle = asyncio.run(manager.retrieve(plan, user_id=9))
    summary = manager.to_legacy(bundle)["retrieval_summary"]

    assert summary["effective_retrievers"] == ["user_docs"]
    assert summary["personal_documents_available"] is True
    assert summary["personal_documents_used"] is False


def test_enhanced_generic_advice_keeps_personal_context_in_manager(monkeypatch):
    from backend.config import settings

    class AdviceRetriever(ScopeRetriever):
        async def search(self, query, top_k=None, where=None):
            return [{
                "chunk_id": "public-advice",
                "title": "专业发展建议",
                "snippet": "大四学生可以结合专业方向规划就业和毕业安排。",
                "score": 0.8,
            }]

        async def search_user_documents(self, query, *, user_id, top_k=None, where=None):
            return [{
                "chunk_id": "private-advice",
                "title": "个人培养方案",
                "snippet": "大四阶段应完成专业课程、毕业实习和毕业设计。",
                "score": 0.8,
                "metadata": {"user_id": user_id},
            }]

    monkeypatch.setattr(settings, "rag_max_retry", 0)
    manager = RetrievalManager(retriever=AdviceRetriever())
    plan = _plan().model_copy(update={
        "original_query": "信计大四学生的建议",
        "standalone_query": "信计大四学生的建议",
        "subquestions": [SubQuestion(
            id="q1",
            query="信计大四学生的建议",
            intent="advice",
            retrievers=["campus_rag", "user_docs"],
        )],
    })

    bundle = asyncio.run(manager.retrieve(plan, user_id=9))
    summary = manager.to_legacy(bundle)["retrieval_summary"]

    assert summary["personal_documents_status"] == "retrieved"
    assert summary["personal_documents_used"] is True
    assert any(item.retriever == "user_docs" for item in bundle.evidences)


def test_enhanced_mode_exposes_personal_retrieval_failure_instead_of_silent_downgrade(
    monkeypatch, caplog
):
    from backend.config import settings

    class BrokenPersonalRetriever(ScopeRetriever):
        async def search_user_documents(self, query, *, user_id, top_k=None, where=None):
            raise ValueError("invalid Chroma metadata filter")

    monkeypatch.setattr(settings, "rag_max_retry", 0)
    manager = RetrievalManager(retriever=BrokenPersonalRetriever())
    plan = _plan()

    with caplog.at_level("INFO", logger="backend.rag.retrieval_manager"):
        bundle = asyncio.run(manager.retrieve(plan, user_id=9))
    summary = manager.to_legacy(bundle)["retrieval_summary"]

    assert summary["retriever_status"]["user_docs"]["status"] == "error"
    assert summary["personal_documents_attempted"] is True
    assert summary["personal_documents_hit"] is False
    assert summary["personal_documents_status"] == "failed"
    assert summary["personal_documents_used"] is False
    assert f"trace_id={plan.trace_id}" in caplog.text
    assert "retriever=user_docs" in caplog.text
    assert "status=error" in caplog.text
    assert "ValueError" in caplog.text
    assert "invalid Chroma metadata filter" not in caplog.text


def test_router_sse_includes_scope_diagnostics_before_retrieval():
    class Planner:
        async def plan(self, *args, **kwargs):
            return _plan()

    class Manager:
        async def retrieve(self, plan, *, user_id=None, history=None):
            return EvidenceBundle(query=plan.query)

        def to_legacy(self, bundle):
            return {"retrieval_summary": {"evidence_assessment": {"status": "unsupported"}}}

    class AnswerGenerator:
        async def generate_stream(self, question, evidence, history=None):
            yield 'data: ' + json.dumps({"type": "done"}) + "\n\n"

    controller = AgentController()
    controller.planner = Planner()
    controller.retrieval_manager = Manager()
    controller.answer_generator = AnswerGenerator()

    async def collect():
        return [chunk async for chunk in controller.handle_stream(
            "课程安排", user_id=9, knowledge_scope="with_personal", has_personal_documents=True
        )]

    first_event = json.loads(asyncio.run(collect())[0].removeprefix("data: ").strip())

    assert first_event["type"] == "router"
    assert first_event["knowledge_scope"] == "with_personal"
    assert first_event["base_retrievers"] == ["campus_rag"]
    assert first_event["effective_retrievers"] == ["campus_rag", "user_docs"]
    assert first_event["personal_documents_available"] is True
    assert first_event["personal_documents_used"] is False
