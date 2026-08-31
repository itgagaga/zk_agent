"""并行检索协调器：负责调用检索器，不负责证据优先级裁决。"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from backend.config import settings
from backend.rag.contracts import Evidence, EvidenceBundle
from backend.rag.evidence_fusion import EvidenceFusion
from backend.rag.evidence_gate import EvidenceAssessment, EvidenceGate
from backend.rag.query_planner import QueryPlanner, RetrievalPlan
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
        self.fusion = fusion or EvidenceFusion(mode=settings.rag_fusion_mode)
        self.gate = gate or EvidenceGate()

    async def retrieve(
        self,
        plan: RetrievalPlan,
        *,
        user_id: int | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> EvidenceBundle:
        query = plan.standalone_query
        tasks: list[tuple[str, str, Any]] = []
        subquestions = plan.subquestions or []
        for subquestion in subquestions:
            for retriever_name in subquestion.retrievers:
                if retriever_name == "campus_rag":
                    tasks.append((subquestion.id, retriever_name, self.retriever.search(subquestion.query)))
                elif retriever_name == "shared_docs":
                    search_shared = getattr(self.retriever, "search_shared_documents", None)
                    if search_shared is None:
                        search_shared = self.retriever.search_documents
                    tasks.append((subquestion.id, retriever_name, search_shared(subquestion.query)))
                elif retriever_name == "user_docs" and user_id is not None:
                    search_user = getattr(self.retriever, "search_user_documents", None)
                    if search_user is None:
                        search_user = self.retriever.search_documents
                    tasks.append((subquestion.id, retriever_name, search_user(subquestion.query, user_id=user_id)))
                elif retriever_name in self.tools:
                    kwargs: dict[str, Any] = {}
                    if retriever_name == "map_route" and history:
                        kwargs["history"] = history
                    tasks.append((subquestion.id, retriever_name, self.tools[retriever_name].run(subquestion.query, **kwargs)))

        # 兼容外部构造的旧计划：只有 retrievers 没有子问题时仍能检索一次。
        if not subquestions:
            subquestions = []
            for retriever_name in plan.retrievers:
                subquestions.append(type("LegacySubQuestion", (), {"id": "q1", "query": query, "retrievers": [retriever_name]})())
            for subquestion in subquestions:
                retriever_name = subquestion.retrievers[0]
                if retriever_name == "campus_rag":
                    tasks.append((subquestion.id, retriever_name, self.retriever.search(query)))
                elif retriever_name == "user_docs" and user_id is not None:
                    tasks.append((subquestion.id, retriever_name, self.retriever.search_documents(query, user_id=user_id)))
                elif retriever_name in self.tools:
                    tasks.append((subquestion.id, retriever_name, self.tools[retriever_name].run(query)))

        results = await asyncio.gather(*(task for _, _, task in tasks), return_exceptions=True)
        evidences: list[Evidence] = []
        failed_retrievers: list[str] = []
        retrieval_errors: dict[str, str] = {}
        candidate_counts: dict[str, int] = defaultdict(int)
        for (subquestion_id, retriever_name, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                failed_retrievers.append(retriever_name)
                continue
            if retriever_name in {"campus_rag", "shared_docs", "user_docs"}:
                for rank, hit in enumerate(result or [], start=1):
                    evidence = Evidence.from_rag_hit(
                        hit,
                        retriever=retriever_name,
                    )
                    evidence.rank = rank
                    if evidence.kind in {"rag", "document"}:
                        if evidence.dense_rank is None and evidence.lexical_rank is None:
                            evidence.dense_rank = hit.get("dense_rank") or (
                                rank if hit.get("retrieval_source") != "lexical" else None
                            )
                        if evidence.lexical_rank is None and hit.get("retrieval_source") == "lexical":
                            evidence.lexical_rank = hit.get("lexical_rank") or rank
                    else:
                        evidence.tool_rank = evidence.tool_rank or rank
                    evidence.metadata["subquestion_id"] = subquestion_id
                    evidences.append(evidence)
                    candidate_counts[retriever_name] += 1
            else:
                tool_result = result or {}
                if tool_result.get("error"):
                    failed_retrievers.append(retriever_name)
                    retrieval_errors[retriever_name] = str(tool_result["error"])
                for rank, item in enumerate(tool_result.get("items", []) or [], start=1):
                    evidence = Evidence.from_tool_item(item, tool=retriever_name)
                    evidence.rank = rank
                    evidence.metadata["subquestion_id"] = subquestion_id
                    evidences.append(evidence)
                    candidate_counts[retriever_name] += 1
        bundle = self.fusion.fuse(
            query,
            evidences,
            retrievers=[name for _, name, _ in tasks],
            trace_id=plan.trace_id,
        )
        bundle.subquestions = list(plan.subquestions)
        bundle.diagnostics["candidate_counts"] = dict(candidate_counts)
        if failed_retrievers:
            bundle.diagnostics["failed_retrievers"] = sorted(set(failed_retrievers))
            bundle.diagnostics["retrieval_failures"] = sorted(set(failed_retrievers))
        if retrieval_errors:
            bundle.diagnostics["retrieval_failures"] = sorted(retrieval_errors)
            bundle.diagnostics["retrieval_errors"] = retrieval_errors
        first_assessment = await self.gate.assess_async(bundle)
        bundle.diagnostics["evidence_assessment_initial"] = first_assessment.model_dump()
        bundle.diagnostics["rescue_attempts"] = 0
        bundle.diagnostics["retry_attempts"] = 0

        # 一次性按 Judge 缺口改写查询；不通过单纯扩大同一查询的 Top-K 伪装重试。
        if settings.rag_max_retry > 0 and first_assessment.should_retry:
            retry_base = plan.standalone_query
            if plan.original_query and plan.original_query not in retry_base:
                retry_base = f"{plan.original_query}；{retry_base}"
            retry_query = QueryPlanner.rewrite_for_retry(
                retry_base,
                first_assessment.missing_information,
                first_assessment.conflicts,
            )
            retry_targets = [
                name for name in plan.retrievers
                if name != "user_docs" or user_id is not None
            ]
            bundle.diagnostics["retry_query"] = retry_query
            bundle.diagnostics["retry_retrievers"] = retry_targets
            try:
                retry_tasks: list[Any] = []
                for retriever_name in retry_targets:
                    if retriever_name == "campus_rag":
                        retry_tasks.append(self.retriever.search(retry_query))
                    elif retriever_name == "shared_docs":
                        search_shared = getattr(self.retriever, "search_shared_documents", None)
                        if search_shared is None:
                            search_shared = self.retriever.search_documents
                        retry_tasks.append(search_shared(retry_query))
                    elif retriever_name == "user_docs" and user_id is not None:
                        search_user = getattr(self.retriever, "search_user_documents", None)
                        if search_user is None:
                            search_user = self.retriever.search_documents
                        retry_tasks.append(search_user(retry_query, user_id=user_id))
                    elif retriever_name in self.tools:
                        retry_tasks.append(self.tools[retriever_name].run(retry_query))
                retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)
            except Exception as exc:
                bundle.diagnostics["retry_error"] = type(exc).__name__
            else:
                rescue_evidences: list[Evidence] = []
                retry_failed: list[str] = []
                for retriever_name, retry_result in zip(retry_targets, retry_results):
                    if isinstance(retry_result, Exception):
                        retry_failed.append(retriever_name)
                        continue
                    if retriever_name in {"campus_rag", "shared_docs", "user_docs"}:
                        for rank, hit in enumerate(retry_result or [], start=1):
                            retry_evidence = Evidence.from_rag_hit(hit, retriever=retriever_name)
                            retry_evidence.rank = rank
                            if retry_evidence.dense_rank is None and retry_evidence.lexical_rank is None:
                                retry_evidence.dense_rank = hit.get("dense_rank") or rank
                            retry_evidence.metadata["subquestion_id"] = (
                                plan.subquestions[0].id if plan.subquestions else "q1"
                            )
                            retry_evidence.metadata["retry_query"] = retry_query
                            rescue_evidences.append(retry_evidence)
                    else:
                        for rank, item in enumerate((retry_result or {}).get("items", []) or [], start=1):
                            retry_evidence = Evidence.from_tool_item(item, tool=retriever_name)
                            retry_evidence.rank = rank
                            retry_evidence.tool_rank = retry_evidence.tool_rank or rank
                            retry_evidence.metadata["subquestion_id"] = (
                                plan.subquestions[0].id if plan.subquestions else "q1"
                            )
                            retry_evidence.metadata["retry_query"] = retry_query
                            rescue_evidences.append(retry_evidence)
                bundle = self.fusion.fuse(
                    plan.query,
                    [*bundle.evidences, *rescue_evidences],
                    retrievers=[name for _, name, _ in tasks],
                    trace_id=plan.trace_id,
                )
                bundle.subquestions = list(plan.subquestions)
                bundle.diagnostics["candidate_counts"] = dict(candidate_counts)
                bundle.diagnostics["evidence_assessment_initial"] = first_assessment.model_dump()
                bundle.diagnostics["retry_query"] = retry_query
                bundle.diagnostics["retry_retrievers"] = retry_targets
                if retrieval_errors:
                    bundle.diagnostics["retrieval_failures"] = sorted(retrieval_errors)
                    bundle.diagnostics["retrieval_errors"] = retrieval_errors
                if failed_retrievers:
                    bundle.diagnostics["retrieval_failures"] = sorted(set(failed_retrievers))
                if retry_failed:
                    bundle.diagnostics["retry_failed_retrievers"] = sorted(set(retry_failed))
                bundle.diagnostics["retry_attempts"] = 1
                bundle.diagnostics["rescue_attempts"] = 1

        assessment = await self.gate.assess_async(bundle)
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
