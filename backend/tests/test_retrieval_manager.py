import asyncio

from backend.rag.evidence_fusion import EvidenceFusion
from backend.rag.query_planner import QueryPlanner
from backend.rag.retrieval_manager import RetrievalManager


class FakeRetriever:
    async def search(self, query, top_k=None, where=None):
        return [{"chunk_id": "campus-1", "title": "政策", "snippet": "官方说明", "score": 0.8}]

    async def search_documents(self, query, top_k=None, where=None, user_id=None):
        return [{"chunk_id": "doc-1", "title": "我的文档", "snippet": "个人说明", "score": 0.7, "metadata": {"doc_id": "doc-1", "user_id": user_id}}]


class FakeTool:
    def __init__(self, name):
        self.name = name

    async def run(self, question, **kwargs):
        return {"tool": self.name, "items": [{"title": "缓考申请表", "file_url": "/late.pdf"}], "total": 1}


def test_manager_runs_requested_retrievers_and_maps_legacy_evidence():
    manager = RetrievalManager(
        retriever=FakeRetriever(),
        tools={"download_search": FakeTool("download_search")},
        fusion=EvidenceFusion(max_items=10),
    )
    plan = QueryPlanner().plan("缓考申请表在哪里下载？", user_id=7)

    bundle = asyncio.run(manager.retrieve(plan, user_id=7))
    legacy = manager.to_legacy(bundle)

    assert {"campus_rag", "download_search"}.issubset(bundle.retrievers)
    assert legacy["rag_hits"][0]["chunk_id"] == "campus-1"
    assert legacy["doc_hits"] == []
    assert legacy["tool_results"][0]["items"][0]["file_url"] == "/late.pdf"
    assert legacy["retrieval_summary"]["independent_source_count"] == 2


def test_manager_rescues_when_first_pass_has_only_wrong_document_type():
    class RescueRetriever:
        async def search(self, query, top_k=None, where=None):
            if "补充检索约束" in query:
                return [{
                    "chunk_id": "undergrad-charter",
                    "title": "2026年普通高考招生章程",
                    "snippet": "招生计划、录取规则和收费标准",
                    "score": 0.8,
                }]
            return [{
                "chunk_id": "master-charter",
                "title": "2026年硕士研究生招生章程",
                "snippet": "研究生报名",
                "score": 0.9,
            }]

        async def search_documents(self, query, top_k=None, where=None, user_id=None):
            return []

    manager = RetrievalManager(retriever=RescueRetriever(), tools={})
    plan = QueryPlanner().plan("2026年本科招生章程主要讲了什么")

    bundle = asyncio.run(manager.retrieve(plan))
    legacy = manager.to_legacy(bundle)

    assert legacy["retrieval_summary"]["rescue_attempts"] == 1
    assert legacy["retrieval_summary"]["evidence_assessment"]["status"] == "supported"
    assert bundle.evidences[0].chunk_id == "undergrad-charter"
