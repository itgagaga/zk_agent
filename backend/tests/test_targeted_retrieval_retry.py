import asyncio

from backend.rag.contracts import EvidenceAssessment, RetrievalPlan, SubQuestion
from backend.rag.query_planner import QueryPlanner
from backend.rag.retrieval_manager import RetrievalManager


class TargetedRetriever:
    def __init__(self):
        self.calls = []

    async def search(self, query, top_k=None, where=None):
        self.calls.append((query, top_k))
        if "补充检索约束" in query:
            return [{
                "chunk_id": "undergrad-charter",
                "doc_id": "undergrad-charter-doc",
                "title": "2026年本科招生章程",
                "snippet": "本科招生计划、录取规则和收费标准",
                "score": 0.8,
            }]
        return [{
            "chunk_id": "master-charter",
            "doc_id": "master-charter-doc",
            "title": "2026年硕士研究生招生章程",
            "snippet": "研究生报名要求",
            "score": 0.9,
        }]


def test_retry_rewrites_query_and_runs_at_most_once():
    retriever = TargetedRetriever()
    manager = RetrievalManager(retriever=retriever, tools={})
    plan = QueryPlanner().plan("2026年本科招生章程主要讲了什么")

    bundle = asyncio.run(manager.retrieve(plan))

    assert len(retriever.calls) == 2
    assert retriever.calls[0][0] != retriever.calls[1][0]
    assert retriever.calls[1][1] is None
    assert bundle.diagnostics["retry_attempts"] == 1
    assert bundle.diagnostics["retry_query"] == retriever.calls[1][0]
    assert bundle.diagnostics["retry_retrievers"] == ["campus_rag"]
    assert bundle.diagnostics["evidence_assessment"]["status"] == "supported"


def test_retry_keeps_history_entities_in_rewritten_query():
    rewritten = QueryPlanner.rewrite_for_retry(
        "白云校区网络报障电话；当前追问：那海珠校区呢",
        ["未覆盖：海珠校区"],
        [],
    )

    assert "白云校区" in rewritten
    assert "海珠校区" in rewritten


def test_personal_only_retry_cannot_expand_to_public_retrievers():
    class ScopeRetryRetriever:
        def __init__(self):
            self.calls = []

        async def search(self, query, top_k=None, where=None):
            self.calls.append(("campus_rag", query))
            return [{"chunk_id": "public", "title": "公开课程", "snippet": "公开资料", "score": 0.8}]

        async def search_user_documents(self, query, *, user_id, top_k=None, where=None):
            self.calls.append(("user_docs", query, user_id))
            return [{
                "chunk_id": "private",
                "title": "个人培养方案",
                "snippet": "个人资料",
                "score": 0.8,
                "metadata": {"user_id": user_id, "doc_id": "private-doc"},
            }]

    class AlwaysRetryGate:
        async def assess_async(self, bundle):
            return EvidenceAssessment(
                status="partial",
                should_retry=True,
                retry_recommended=True,
                missing_information=["课程安排"],
            )

        def rank(self, query, evidences):
            return list(evidences)

    retriever = ScopeRetryRetriever()
    plan = RetrievalPlan(
        original_query="课程安排",
        standalone_query="课程安排",
        subquestions=[SubQuestion(
            id="q1",
            query="课程安排",
            intent="major",
            retrievers=["campus_rag"],
        )],
        knowledge_scope="personal_only",
        base_retrievers=["campus_rag"],
        retrievers=["campus_rag"],
    )

    bundle = asyncio.run(RetrievalManager(
        retriever=retriever,
        tools={},
        gate=AlwaysRetryGate(),
    ).retrieve(plan, user_id=7))

    assert all(call[0] == "user_docs" for call in retriever.calls)
    assert all(call[-1] == 7 for call in retriever.calls)
    assert bundle.diagnostics["retry_retrievers"] == ["user_docs"]
