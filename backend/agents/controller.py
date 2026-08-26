"""Agent 主控模块。

轻量检索编排：
- QueryPlanner：声明需要尝试的检索器
- RetrievalManager：并行取证、补检索与证据门控
- AnswerGenerator：基于融合后的证据生成回答
"""
from __future__ import annotations

from typing import Any

from backend.agents.answer_generator import AnswerGenerator
from backend.agents.fallback import FallbackHandler
from backend.rag.retriever import RAGRetriever
from backend.rag.query_planner import QueryPlanner, RetrievalPlan
from backend.rag.retrieval_manager import RetrievalManager
from backend.tools.contact_tool import ContactTool
from backend.tools.download_tool import DownloadTool
from backend.tools.major_tool import MajorTool
from backend.tools.service_link_tool import ServiceLinkTool
from backend.tools.weather_tool import WeatherTool
from backend.tools.academic_search_tool import AcademicSearchTool
from backend.tools.map_tool import MapTool


class AgentController:
    """Agent 主控。"""

    def __init__(self) -> None:
        self.retriever = RAGRetriever()
        self.answer_generator = AnswerGenerator()
        self.fallback = FallbackHandler()
        self.tools: dict[str, Any] = {
            "major_search": MajorTool(),
            "download_search": DownloadTool(),
            "contact_search": ContactTool(),
            "service_link_search": ServiceLinkTool(),
            "weather_search": WeatherTool(),
            "academic_search": AcademicSearchTool(),
            "map_route": MapTool(),
        }
        self.planner = QueryPlanner()
        self.retrieval_manager = RetrievalManager(
            retriever=self.retriever,
            tools=self.tools,
        )

    async def _gather_planned_evidence(
        self,
        question: str,
        plan: RetrievalPlan,
        *,
        history: list[dict[str, str]] | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """新编排路径：并行取证后统一映射为过渡期 evidence 字典。"""
        bundle = await self.retrieval_manager.retrieve(
            plan,
            user_id=user_id,
            history=history,
        )
        evidence = self.retrieval_manager.to_legacy(bundle)
        evidence.update(
            {
                "question": question,
                "route_mode": "planned",
                "evidence_mode": "composite",
                # Deprecated compatibility fields for older API consumers.
                # The active pipeline never reads these fields for selection.
                "evidence_priority": "composite",
                "supervisor_reason": "Deprecated: evidence is fused and gated by RetrievalManager",
                "supervisor_agents": bundle.retrievers,
                "retrieval_bundle": bundle,
            }
        )
        return evidence

    async def handle(
        self,
        question: str,
        *,
        session_id: str | None = None,
        user_role: str = "student",
        history: list[dict[str, str]] | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        plan = self.planner.plan(question, user_id=user_id)
        print(
            f"[Agent] Planner 检索器={plan.retrievers} "
            f"查询='{plan.normalized_query}' (原始: '{question}')"
        )
        evidence = await self._gather_planned_evidence(
            question, plan, history=history, user_id=user_id
        )
        assessment = (evidence.get("retrieval_summary") or {}).get("evidence_assessment") or {}
        if assessment.get("status") == "unsupported":
            fallback = self.fallback.no_evidence(question)
            fallback["retrieval_summary"] = evidence.get("retrieval_summary")
            return fallback
        result = await self.answer_generator.generate(question, evidence, history=history)

        if not result.get("sources") and self.fallback.enabled:
            return self.fallback.no_evidence(question)

        result["route_mode"] = "planned"
        result["router_source"] = "planner"
        result["evidence_mode"] = evidence.get("evidence_mode", "composite")
        # Deprecated compatibility fields; no longer used for evidence selection.
        result["evidence_priority"] = evidence.get("evidence_priority")
        result["supervisor_reason"] = evidence.get("supervisor_reason")
        if evidence.get("retrieval_summary"):
            result["retrieval_summary"] = evidence["retrieval_summary"]
        result["agents_used"] = evidence.get("supervisor_agents", [])
        return result

    async def handle_stream(
        self,
        question: str,
        *,
        session_id: str | None = None,
        user_role: str = "student",
        history: list[dict[str, str]] | None = None,
        user_id: int | None = None,
    ):
        import json

        plan = self.planner.plan(question, user_id=user_id)
        print(
            f"[Agent] Planner 检索器={plan.retrievers} "
            f"查询='{plan.normalized_query}' (原始: '{question}')"
        )
        router_evt = {
            "type": "router",
            "source": "planner",
            "mode": "parallel",
            "intents": plan.retrievers,
            "collab_reason": "并行检索后证据融合",
        }
        yield f"data: {json.dumps(router_evt, ensure_ascii=False)}\n\n"

        evidence = await self._gather_planned_evidence(
            question, plan, history=history, user_id=user_id
        )

        yield f"data: {json.dumps({'type': 'retrieval', **evidence.get('retrieval_summary', {})}, ensure_ascii=False)}\n\n"

        assessment = (evidence.get("retrieval_summary") or {}).get("evidence_assessment") or {}
        if assessment.get("status") == "unsupported":
            fb = self.fallback.no_evidence(question)
            meta = {
                "type": "meta",
                "confidence": "low",
                "sources": fb.get("sources", []),
                "attachments": [],
                "tools_used": [],
                "fallback": True,
                "retrieval_summary": evidence.get("retrieval_summary"),
            }
            yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
            yield f'data: {json.dumps({"type": "token", "content": fb.get("answer", "")}, ensure_ascii=False)}\n\n'
            yield f'data: {json.dumps({"type": "done"}, ensure_ascii=False)}\n\n'
            return

        async for chunk in self.answer_generator.generate_stream(question, evidence, history=history):
            yield chunk
