import asyncio
import json

from backend.agents.controller import AgentController
from backend.rag.contracts import EvidenceBundle, RetrievalPlan, SubQuestion


def _plan(scope, retrievers, status):
    return RetrievalPlan(
        original_query="课程建议",
        standalone_query="课程建议",
        subquestions=[SubQuestion(id="q1", query="课程建议", retrievers=retrievers)],
        knowledge_scope=scope,
        base_retrievers=["campus_rag"],
        retrievers=list(retrievers),
        diagnostics={"personal_documents_status": status},
    )


class Planner:
    def __init__(self, plan):
        self.plan_value = plan

    async def plan(self, *args, **kwargs):
        return self.plan_value


class Manager:
    def __init__(self, summary):
        self.summary = summary

    async def retrieve(self, plan, *, user_id=None, history=None):
        return EvidenceBundle(query=plan.query)

    def to_legacy(self, bundle):
        return {
            "rag_hits": [{"title": "校园资料", "snippet": "标准回答依据"}],
            "doc_hits": [],
            "tool_results": [],
            "retrieval_summary": self.summary,
        }


class AnswerGenerator:
    async def generate(self, question, evidence, history=None):
        return {"answer": "标准回答", "sources": [{"title": "校园资料"}], "fallback": False}

    async def generate_stream(self, question, evidence, history=None):
        yield 'data: ' + json.dumps({"type": "token", "content": "标准回答"}, ensure_ascii=False) + "\n\n"
        yield 'data: ' + json.dumps({"type": "done"}) + "\n\n"


def _controller(plan, summary):
    controller = AgentController()
    controller.planner = Planner(plan)
    controller.retrieval_manager = Manager(summary)
    controller.answer_generator = AnswerGenerator()
    return controller


def test_enhanced_personal_failure_keeps_public_answer_with_explicit_notice():
    summary = {
        "knowledge_scope": "with_personal",
        "personal_documents_status": "failed",
        "personal_documents_used": False,
        "evidence_assessment": {"status": "supported"},
    }
    controller = _controller(
        _plan("with_personal", ["campus_rag", "user_docs"], "failed"),
        summary,
    )

    result = asyncio.run(controller.handle("课程建议", user_id=7))

    assert "个人知识库本次检索失败" in result["answer"]
    assert "仅基于标准资料" in result["answer"]
    assert "标准回答" in result["answer"]
    assert result["fallback"] is False


def test_personal_only_no_hit_returns_private_only_fallback():
    summary = {
        "knowledge_scope": "personal_only",
        "personal_documents_status": "no_hit",
        "personal_documents_used": False,
        "evidence_assessment": {"status": "unsupported"},
    }
    controller = _controller(
        _plan("personal_only", ["user_docs"], "no_hit"),
        summary,
    )

    result = asyncio.run(controller.handle("课程建议", user_id=7))

    assert result["fallback"] is True
    assert "个人知识库中没有找到" in result["answer"]
    assert "公开资料" not in result["answer"]


def test_enhanced_personal_failure_streams_explicit_notice():
    summary = {
        "knowledge_scope": "with_personal",
        "personal_documents_status": "failed",
        "personal_documents_used": False,
        "evidence_assessment": {"status": "supported"},
    }
    controller = _controller(
        _plan("with_personal", ["campus_rag", "user_docs"], "failed"),
        summary,
    )

    async def collect():
        return [chunk async for chunk in controller.handle_stream("课程建议", user_id=7)]

    events = [
        json.loads(line[6:])
        for chunk in asyncio.run(collect())
        for line in chunk.splitlines()
        if line.startswith("data: ")
    ]
    token_text = "".join(event["content"] for event in events if event["type"] == "token")

    assert "个人知识库本次检索失败" in token_text
    assert "标准回答" in token_text
