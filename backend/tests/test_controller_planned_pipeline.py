import asyncio
import json

from backend.agents.controller import AgentController
from backend.rag.contracts import Evidence, EvidenceBundle
from backend.rag.query_planner import QueryPlanner


class FakeManager:
    def __init__(self):
        self.bundle = EvidenceBundle(
            query="缓考申请表",
            evidences=[Evidence.from_rag_hit({"chunk_id": "campus-1", "title": "缓考政策", "snippet": "官网说明", "score": 0.9})],
            retrievers=["campus_rag"],
            coverage=1.0,
            independent_source_count=1,
        )

    async def retrieve(self, plan, *, user_id=None, history=None):
        return self.bundle

    def to_legacy(self, bundle):
        return {
            "rag_hits": [dict(bundle.evidences[0].raw)],
            "doc_hits": [],
            "tool_results": [],
            "retrieval_summary": {
                "retrievers": bundle.retrievers,
                "coverage": bundle.coverage,
                "independent_source_count": bundle.independent_source_count,
            },
        }


class FakeAnswerGenerator:
    async def generate(self, question, evidence, history=None):
        return {"answer": "基于官网说明", "sources": [{"title": "缓考政策"}], "fallback": False}

    async def generate_stream(self, question, evidence, history=None):
        yield 'data: ' + json.dumps({"type": "meta", "sources": [{"title": "缓考政策"}], "retrieval_summary": evidence["retrieval_summary"]}, ensure_ascii=False) + "\n\n"
        yield 'data: ' + json.dumps({"type": "done"}) + "\n\n"


def test_controller_uses_planner_pipeline_without_exclusive_supervisor_filter():
    controller = AgentController()
    controller.planner = QueryPlanner()
    controller.retrieval_manager = FakeManager()
    controller.answer_generator = FakeAnswerGenerator()

    result = asyncio.run(controller.handle("缓考申请表在哪里下载？"))

    assert result["sources"][0]["title"] == "缓考政策"
    assert result["router_source"] == "planner"
    assert result["retrieval_summary"]["coverage"] == 1.0
