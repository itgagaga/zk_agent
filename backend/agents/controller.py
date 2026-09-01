"""Agent 主控模块。

轻量检索编排：
- QueryPlanner：声明需要尝试的检索器
- RetrievalManager：并行取证、补检索与证据门控
- AnswerGenerator：基于融合后的证据生成回答
"""
from __future__ import annotations

import logging
import time
from typing import Any

from backend.agents.answer_generator import AnswerGenerator
from backend.agents.fallback import FallbackHandler
from backend.rag.retriever import RAGRetriever
from backend.rag.query_planner import QueryPlanner, RetrievalPlan
from backend.rag.retrieval_manager import RetrievalManager
from backend.rag.contracts import KnowledgeScope
from backend.tools.contact_tool import ContactTool
from backend.tools.download_tool import DownloadTool
from backend.tools.major_tool import MajorTool
from backend.tools.service_link_tool import ServiceLinkTool
from backend.tools.weather_tool import WeatherTool
from backend.tools.academic_search_tool import AcademicSearchTool
from backend.tools.map_tool import MapTool
from backend.tools.job_tool import JobTool
from backend.tools.news_tool import NewsTool


logger = logging.getLogger(__name__)


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
            "job_search": JobTool(),
            "news_search": NewsTool(),
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
        started_at = time.perf_counter()
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
        logger.info(
            "chat_stage trace_id=%s stage=retrieval_mapping duration_ms=%.1f "
            "evidence_count=%s",
            bundle.trace_id,
            (time.perf_counter() - started_at) * 1000,
            len(bundle.evidences),
        )
        return evidence

    @staticmethod
    def _generation_question(question: str, evidence: dict[str, Any]) -> str:
        """把 Evidence Judge 的边界传给生成器，避免 partial 被写成完整答案。"""
        assessment = (evidence.get("retrieval_summary") or {}).get("evidence_assessment") or {}
        if assessment.get("status") != "partial":
            return question
        missing = assessment.get("missing_information") or []
        missing_text = "；".join(str(item) for item in missing[:8]) or "部分信息未被证据覆盖"
        return (
            f"{question}\n\n"
            "【证据边界】当前资料只支持问题的一部分。只回答已有证据明确支持的内容，"
            f"并明确说明未覆盖项：{missing_text}。不得根据常识补全或声称问题已完整解决。"
        )

    @staticmethod
    def _scope_diagnostics(plan: RetrievalPlan) -> dict[str, Any]:
        """返回路由阶段可展示的范围信息；此时尚未知道是否命中个人资料。"""
        requested = plan.knowledge_scope != "auto"
        return {
            "knowledge_scope": plan.knowledge_scope,
            "base_retrievers": list(plan.base_retrievers),
            "effective_retrievers": list(plan.retrievers),
            "personal_documents_requested": requested,
            "personal_documents_available": requested and not bool(
                plan.diagnostics.get("personal_documents_empty")
            ),
            "personal_documents_used": False,
        }

    @staticmethod
    def _personal_scope_notice(summary: dict[str, Any]) -> str | None:
        """生成面向用户的个人资料提示，不暴露内部异常。"""
        scope = summary.get("knowledge_scope")
        status = summary.get("personal_documents_status")
        if scope == "with_personal" and status == "failed":
            return "【个人资料提示】个人知识库本次检索失败，以下回答仅基于标准资料。"
        return None

    @staticmethod
    def _private_scope_fallback(summary: dict[str, Any]) -> str | None:
        """私有模式的专属兜底文案，保证不会暗示使用了公共资料。"""
        if summary.get("knowledge_scope") != "personal_only":
            return None
        status = summary.get("personal_documents_status")
        if status == "failed":
            return "你的个人知识库本次检索失败，暂时无法基于个人资料回答。"
        if status == "empty_library":
            return "你的个人知识库当前为空，暂时无法基于个人资料回答。"
        if status in {"no_hit", "skipped"}:
            return "你的个人知识库中没有找到与该问题直接相关的资料，暂时无法基于个人资料回答。"
        return None

    async def handle(
        self,
        question: str,
        *,
        session_id: str | None = None,
        user_role: str = "student",
        history: list[dict[str, str]] | None = None,
        user_id: int | None = None,
        context_hint: str | None = None,
        knowledge_scope: KnowledgeScope = "auto",
        has_personal_documents: bool = False,
    ) -> dict[str, Any]:
        planner_started_at = time.perf_counter()
        plan = await self.planner.plan(
            question,
            history=history,
            user_id=user_id,
            context_hint=context_hint,
            knowledge_scope=knowledge_scope,
            has_personal_documents=has_personal_documents,
        )
        logger.info(
            "chat_stage trace_id=%s stage=planner duration_ms=%.1f source=%s "
            "retriever_count=%s",
            plan.trace_id,
            (time.perf_counter() - planner_started_at) * 1000,
            plan.planner_source,
            len(plan.retrievers),
        )
        print(
            f"[Agent] Planner 检索器={plan.retrievers} "
            f"查询='{plan.normalized_query}' (原始: '{question}')"
        )
        evidence = await self._gather_planned_evidence(
            question, plan, history=history, user_id=user_id
        )
        summary = evidence.get("retrieval_summary") or {}
        assessment = summary.get("evidence_assessment") or {}
        if assessment.get("status") == "unsupported":
            fallback = self.fallback.no_evidence(
                question,
                message=self._private_scope_fallback(summary),
            )
            fallback["retrieval_summary"] = summary
            return fallback
        generation_started_at = time.perf_counter()
        result = await self.answer_generator.generate(
            self._generation_question(question, evidence), evidence, history=history
        )
        logger.info(
            "chat_stage trace_id=%s stage=answer_generation duration_ms=%.1f "
            "source_count=%s",
            plan.trace_id,
            (time.perf_counter() - generation_started_at) * 1000,
            len(result.get("sources") or []),
        )

        if not result.get("sources") and self.fallback.enabled:
            fallback = self.fallback.no_evidence(question)
            notice = self._personal_scope_notice(summary)
            if notice:
                fallback["answer"] = f"{notice}\n\n{fallback['answer']}"
            fallback["retrieval_summary"] = summary
            return fallback

        notice = self._personal_scope_notice(summary)
        if notice:
            result["answer"] = f"{notice}\n\n{result.get('answer', '')}"

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
        context_hint: str | None = None,
        knowledge_scope: KnowledgeScope = "auto",
        has_personal_documents: bool = False,
    ):
        import json

        planner_started_at = time.perf_counter()
        plan = await self.planner.plan(
            question,
            history=history,
            user_id=user_id,
            context_hint=context_hint,
            knowledge_scope=knowledge_scope,
            has_personal_documents=has_personal_documents,
        )
        logger.info(
            "chat_stage trace_id=%s stage=planner duration_ms=%.1f source=%s "
            "retriever_count=%s",
            plan.trace_id,
            (time.perf_counter() - planner_started_at) * 1000,
            plan.planner_source,
            len(plan.retrievers),
        )
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
        router_evt.update(self._scope_diagnostics(plan))
        yield f"data: {json.dumps(router_evt, ensure_ascii=False)}\n\n"

        evidence = await self._gather_planned_evidence(
            question, plan, history=history, user_id=user_id
        )

        yield f"data: {json.dumps({'type': 'retrieval', **evidence.get('retrieval_summary', {})}, ensure_ascii=False)}\n\n"

        summary = evidence.get("retrieval_summary") or {}
        assessment = summary.get("evidence_assessment") or {}
        if assessment.get("status") == "unsupported":
            fb = self.fallback.no_evidence(
                question,
                message=self._private_scope_fallback(summary),
            )
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

        notice = self._personal_scope_notice(summary)
        if notice:
            yield f'data: {json.dumps({"type": "token", "content": notice + "\n\n"}, ensure_ascii=False)}\n\n'

        generation_started_at = time.perf_counter()
        try:
            async for chunk in self.answer_generator.generate_stream(
                self._generation_question(question, evidence), evidence, history=history
            ):
                yield chunk
        finally:
            logger.info(
                "chat_stage trace_id=%s stage=answer_generation_stream duration_ms=%.1f",
                plan.trace_id,
                (time.perf_counter() - generation_started_at) * 1000,
            )
