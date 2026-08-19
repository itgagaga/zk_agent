"""并行检索协调器：负责调用检索器，不负责证据优先级裁决。"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from backend.rag.contracts import Evidence, EvidenceBundle
from backend.rag.evidence_fusion import EvidenceFusion
from backend.rag.evidence_gate import EvidenceAssessment, EvidenceGate
from backend.rag.query_planner import RetrievalPlan
from backend.rag.retriever import RAGRetriever


class RetrievalManager:
    def __init__(
        self,
        *,
        retriever: RAGRetriever | Any | None = None,
        tools: dict[str, Any] | None = None,
        fusion: EvidenceFusion | None = None,
        gate: EvidenceGate | None = None,
    ) -> None:
        self.retriever = retriever or RAGRetriever()
        self.tools = tools or {}
        self.fusion = fusion or EvidenceFusion()
        self.gate = gate or EvidenceGate()

    async def retrieve(
        self,
        plan: RetrievalPlan,
        *,
        user_id: int | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> EvidenceBundle:
        query = plan.normalized_query
        tasks: list[tuple[str, Any]] = []
        for retriever_name in plan.retrievers:
            if retriever_name == "campus_rag":
                tasks.append((retriever_name, self.retriever.search(query)))
            elif retriever_name == "user_docs" and user_id is not None:
                tasks.append((retriever_name, self.retriever.search_documents(query, user_id=user_id)))
            elif retriever_name in self.tools:
                kwargs: dict[str, Any] = {}
                if retriever_name == "map_route" and history:
                    kwargs["history"] = history
                tasks.append((retriever_name, self.tools[retriever_name].run(plan.query, **kwargs)))

        results = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
        evidences: list[Evidence] = []
        for (retriever_name, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                continue
            if retriever_name in {"campus_rag", "user_docs"}:
                for rank, hit in enumerate(result or [], start=1):
                    evidence = Evidence.from_rag_hit(
                        hit,
                        retriever="campus_rag" if retriever_name == "campus_rag" else "user_docs",
                    )
                    evidence.rank = rank
                    evidences.append(evidence)
            else:
                for rank, item in enumerate((result or {}).get("items", []) or [], start=1):
                    evidence = Evidence.from_tool_item(item, tool=retriever_name)
                    evidence.rank = rank
                    evidences.append(evidence)
        bundle = self.fusion.fuse(
            plan.query,
            evidences,
            retrievers=[name for name, _ in tasks],
            trace_id=plan.trace_id,
        )
        first_assessment = self.gate.assess(bundle)
        bundle.diagnostics["evidence_assessment_initial"] = first_assessment.model_dump()
        bundle.diagnostics["rescue_attempts"] = 0

        # 一次性扩大召回：解决“有候选但核心文档被 Top-K 挤掉”，不进入循环。
        if first_assessment.status == "needs_more" and "campus_rag" in plan.retrievers:
            try:
                rescue_hits = await self.retriever.search(
                    plan.normalized_query,
                    top_k=max(20, len(bundle.evidences) * 2),
                )
            except Exception as exc:
                bundle.diagnostics["rescue_error"] = type(exc).__name__
            else:
                rescue_evidences: list[Evidence] = []
                for rank, hit in enumerate(rescue_hits or [], start=1):
                    rescue_evidence = Evidence.from_rag_hit(hit, retriever="campus_rag")
                    rescue_evidence.rank = rank
                    rescue_evidences.append(rescue_evidence)
                bundle = self.fusion.fuse(
                    plan.query,
                    [*bundle.evidences, *rescue_evidences],
                    retrievers=[name for name, _ in tasks],
                    trace_id=plan.trace_id,
                )
                bundle.diagnostics["rescue_attempts"] = 1

        assessment = self.gate.assess(bundle)
        bundle.evidences = self.gate.rank(bundle.query, bundle.evidences)
        bundle.diagnostics["evidence_assessment"] = assessment.model_dump()
        return bundle

    @staticmethod
    def to_legacy(bundle: EvidenceBundle) -> dict[str, Any]:
        """过渡期映射为旧 AnswerGenerator/controller 所需的 evidence 字典。"""
        rag_hits: list[dict[str, Any]] = []
        doc_hits: list[dict[str, Any]] = []
        tool_items: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for evidence in bundle.evidences:
            if evidence.kind in {"rag", "document"}:
                raw = dict(evidence.raw)
                raw.setdefault("score", evidence.score)
                (doc_hits if evidence.kind == "document" else rag_hits).append(raw)
            else:
                tool_items[evidence.retriever].append(dict(evidence.raw))
        tool_results = [
            {"tool": name, "items": items, "total": len(items)}
            for name, items in sorted(tool_items.items())
        ]
        return {
            "rag_hits": rag_hits,
            "doc_hits": doc_hits,
            "tool_results": tool_results,
            "tool_result": tool_results[0] if tool_results else None,
            "retrieval_summary": {
                "retrievers": bundle.retrievers,
                "coverage": bundle.coverage,
                "independent_source_count": bundle.independent_source_count,
                "fallback": bundle.fallback,
                "trace_id": bundle.trace_id,
                "evidence_assessment": bundle.diagnostics.get("evidence_assessment"),
                "rescue_attempts": bundle.diagnostics.get("rescue_attempts", 0),
            },
        }
