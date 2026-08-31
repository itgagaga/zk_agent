import asyncio

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

