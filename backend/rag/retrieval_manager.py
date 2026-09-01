"""并行检索协调器：负责调用检索器，不负责证据优先级裁决。"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any

from backend.config import settings
from backend.rag.contracts import Evidence, EvidenceBundle, KnowledgeScope, RetrievalPlan, SubQuestion
from backend.rag.evidence_fusion import EvidenceFusion
from backend.rag.evidence_gate import EvidenceAssessment, EvidenceGate
from backend.rag.personal_evidence_policy import PersonalEvidencePolicy
from backend.rag.query_planner import QueryPlanner
from backend.rag.retriever import RAGRetriever


logger = logging.getLogger(__name__)


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
        self.personal_policy = PersonalEvidencePolicy()

    async def retrieve(
        self,
        plan: RetrievalPlan,
        *,
        user_id: int | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> EvidenceBundle:
        started_at = time.perf_counter()
        query = plan.standalone_query
        tasks: list[tuple[str, str, Any]] = []
        subquestions = self._scoped_subquestions(plan, user_id=user_id)
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

        results = await asyncio.gather(*(task for _, _, task in tasks), return_exceptions=True)
        logger.info(
            "retrieval_stage trace_id=%s stage=initial_parallel duration_ms=%.1f "
            "task_count=%s",
            plan.trace_id,
            (time.perf_counter() - started_at) * 1000,
            len(tasks),
        )
        evidences: list[Evidence] = []
        failed_retrievers: list[str] = []
        retrieval_errors: dict[str, str] = {}
        candidate_counts: dict[str, int] = defaultdict(int)
        retriever_status: dict[str, dict[str, Any]] = {}

        def record_attempt(
            retriever_name: str,
            *,
            candidate_count: int = 0,
            error_type: str | None = None,
            stage: str,
        ) -> None:
            entry = retriever_status.setdefault(
                retriever_name,
                {"attempted": True, "attempts": 0, "candidate_count": 0, "_errors": []},
            )
            entry["attempted"] = True
            entry["attempts"] += 1
            entry["candidate_count"] += candidate_count
            if error_type:
                entry["_errors"].append({"type": error_type, "stage": stage})

        for (subquestion_id, retriever_name, _), result in zip(tasks, results):
            attempt_candidates = 0
            attempt_error_type: str | None = None
            if isinstance(result, Exception):
                failed_retrievers.append(retriever_name)
                attempt_error_type = type(result).__name__
                retrieval_errors[retriever_name] = attempt_error_type
                record_attempt(
                    retriever_name,
                    error_type=attempt_error_type,
                    stage="initial",
                )
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
                    attempt_candidates += 1
            else:
                tool_result = result or {}
                if tool_result.get("error"):
                    failed_retrievers.append(retriever_name)
                    retrieval_errors[retriever_name] = str(tool_result["error"])
                    attempt_error_type = "tool_error"
                for rank, item in enumerate(tool_result.get("items", []) or [], start=1):
                    evidence = Evidence.from_tool_item(item, tool=retriever_name)
                    evidence.rank = rank
                    evidence.metadata["subquestion_id"] = subquestion_id
                    evidences.append(evidence)
                    candidate_counts[retriever_name] += 1
                    attempt_candidates += 1
            record_attempt(
                retriever_name,
                candidate_count=attempt_candidates,
                error_type=attempt_error_type,
                stage="initial",
            )
        candidate_limit = (
            settings.rag_candidate_safety_max
            if plan.knowledge_scope in {"with_personal", "personal_only"}
            and settings.rag_personal_priority_policy == "adaptive"
            else self.fusion.max_items
        )
        bundle = self.fusion.fuse(
            query,
            evidences,
            retrievers=[name for _, name, _ in tasks],
            trace_id=plan.trace_id,
            max_items=candidate_limit,
        )
        # 后续评估、重试和诊断都必须以真正执行过的有效子问题为准。
        bundle.subquestions = list(subquestions)
        # Evidence Gate 在最终范围诊断生成前也需要知道本次请求的资料范围。
        bundle.diagnostics["knowledge_scope"] = plan.knowledge_scope
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
            retry_targets = list(dict.fromkeys(
                name
                for subquestion in subquestions
                for name in subquestion.retrievers
            ))
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
                    retry_candidates = 0
                    if isinstance(retry_result, Exception):
                        retry_failed.append(retriever_name)
                        retrieval_errors[retriever_name] = type(retry_result).__name__
                        record_attempt(
                            retriever_name,
                            error_type=type(retry_result).__name__,
                            stage="retry",
                        )
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
                            retry_candidates += 1
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
                            retry_candidates += 1
                    record_attempt(
                        retriever_name,
                        candidate_count=retry_candidates,
                        error_type=(
                            "tool_error"
                            if isinstance(retry_result, dict) and retry_result.get("error")
                            else None
                        ),
                        stage="retry",
                    )
                bundle = self.fusion.fuse(
                    plan.query,
                    [*bundle.evidences, *rescue_evidences],
                    retrievers=[name for _, name, _ in tasks],
                    trace_id=plan.trace_id,
                    max_items=candidate_limit,
                )
                bundle.subquestions = list(subquestions)
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
        before_answer_filter = len(bundle.evidences)
        filter_for_answer = getattr(self.gate, "filter_for_answer", None)
        if callable(filter_for_answer):
            bundle.evidences = filter_for_answer(bundle, assessment)
        if len(bundle.evidences) < before_answer_filter:
            bundle.diagnostics["filtered_irrelevant_evidence"] = before_answer_filter - len(bundle.evidences)
        selected_evidences, personal_relevance, selection_diagnostics = self.personal_policy.select(
            bundle,
            assessment,
        )
        bundle.evidences = selected_evidences
        bundle.diagnostics["personal_relevance"] = [
            item.model_dump() for item in personal_relevance
        ]
        bundle.diagnostics["evidence_selection"] = selection_diagnostics
        assess_sync = getattr(self.gate, "assess", None)
        if callable(assess_sync):
            assessment = assess_sync(bundle)
        for retriever_name in list(dict.fromkeys(
            target
            for subquestion in subquestions
            for target in subquestion.retrievers
        )):
            if retriever_name not in retriever_status:
                retriever_status[retriever_name] = {
                    "status": "skipped",
                    "attempted": False,
                    "attempts": 0,
                    "candidate_count": 0,
                }
        for entry in retriever_status.values():
            errors = entry.pop("_errors", [])
            if errors:
                entry["status"] = "error"
                entry["error_type"] = errors[0]["type"]
                entry["error_stage"] = errors[0]["stage"]
            elif entry["candidate_count"] > 0:
                entry["status"] = "success"
            else:
                entry["status"] = "empty"
        bundle.diagnostics["retriever_status"] = retriever_status
        scope_diagnostics = self._scope_diagnostics(
            plan, subquestions, bundle, retriever_status
        )
        bundle.diagnostics.update(scope_diagnostics)
        bundle.diagnostics["evidence_assessment"] = assessment.model_dump()
        for retriever_name, status in sorted(retriever_status.items()):
            logger.info(
                "retrieval trace_id=%s retriever=%s status=%s attempted=%s "
                "attempts=%s candidate_count=%s error_type=%s error_stage=%s",
                plan.trace_id,
                retriever_name,
                status.get("status"),
                status.get("attempted", False),
                status.get("attempts", 0),
                status.get("candidate_count", 0),
                status.get("error_type", ""),
                status.get("error_stage", ""),
            )
        logger.info(
            "retrieval_scope trace_id=%s scope=%s personal_status=%s "
            "personal_attempted=%s personal_hit=%s personal_used=%s",
            plan.trace_id,
            scope_diagnostics["knowledge_scope"],
            scope_diagnostics["personal_documents_status"],
            scope_diagnostics["personal_documents_attempted"],
            scope_diagnostics["personal_documents_hit"],
            scope_diagnostics["personal_documents_used"],
        )
        logger.info(
            "retrieval_stage trace_id=%s stage=complete duration_ms=%.1f "
            "evidence_count=%s retry_attempts=%s",
            plan.trace_id,
            (time.perf_counter() - started_at) * 1000,
            len(bundle.evidences),
            bundle.diagnostics.get("retry_attempts", 0),
        )
        return bundle

    @staticmethod
    def _scope_diagnostics(
        plan: RetrievalPlan,
        subquestions: list[SubQuestion],
        bundle: EvidenceBundle,
        retriever_status: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """生成可安全返回给前端的资料范围诊断，不包含私有文档内容。"""
        base_retrievers = list(dict.fromkeys(
            target for target in (plan.base_retrievers or [
                target
                for source in plan.subquestions
                for target in source.retrievers
            ])
            if target != "user_docs"
        ))
        effective_retrievers = list(dict.fromkeys(
            target
            for subquestion in subquestions
            for target in subquestion.retrievers
        ))
        requested = plan.knowledge_scope != "auto"
        available = requested and not bool(plan.diagnostics.get("personal_documents_empty"))
        used = any(evidence.retriever == "user_docs" for evidence in bundle.evidences)
        user_status = (retriever_status or {}).get("user_docs")
        attempted = bool(user_status and user_status.get("attempted"))
        hit = bool(user_status and user_status.get("candidate_count", 0) > 0)
        if plan.knowledge_scope == "auto":
            personal_status = "not_requested"
        elif plan.diagnostics.get("personal_documents_empty"):
            personal_status = "empty_library"
        elif user_status and user_status.get("status") == "error":
            personal_status = "failed"
        elif hit:
            personal_status = "retrieved"
        elif attempted:
            personal_status = "no_hit"
        else:
            personal_status = "skipped"
        return {
            "knowledge_scope": plan.knowledge_scope,
            "base_retrievers": base_retrievers,
            "effective_retrievers": effective_retrievers,
            "personal_documents_requested": requested,
            "personal_documents_available": available,
            "personal_documents_attempted": attempted,
            "personal_documents_hit": hit,
            "personal_documents_status": personal_status,
            "personal_documents_used": used,
        }

    @staticmethod
    def _scoped_subquestions(
        plan: RetrievalPlan,
        *,
        user_id: int | None,
    ) -> list[SubQuestion]:
        """在实际调用前再次应用资料范围，防止外部/过期计划越权。"""
        scope: KnowledgeScope = plan.knowledge_scope
        if scope not in {"auto", "with_personal", "personal_only"}:
            raise ValueError(f"不支持的 knowledge_scope: {scope}")
        if scope != "auto" and user_id is None:
            raise PermissionError("个人资料范围需要登录")

        source_subquestions = list(plan.subquestions)
        if not source_subquestions and plan.retrievers:
            source_subquestions = [SubQuestion(
                id="q1",
                query=plan.standalone_query,
                retrievers=list(plan.retrievers),
            )]

        empty_personal_library = bool(plan.diagnostics.get("personal_documents_empty"))
        scoped: list[SubQuestion] = []
        for subquestion in source_subquestions:
            public_targets = list(dict.fromkeys(
                target for target in subquestion.retrievers if target != "user_docs"
            ))
            if scope == "auto":
                targets = public_targets
                requires_private = False
            elif scope == "with_personal":
                targets = public_targets if empty_personal_library else [*public_targets, "user_docs"]
                requires_private = not empty_personal_library
            elif empty_personal_library:
                targets = []
                requires_private = True
            else:
                targets = ["user_docs"]
                requires_private = True
            scoped.append(subquestion.model_copy(update={
                "retrievers": list(dict.fromkeys(targets)),
                "requires_private_context": requires_private,
            }))
        return scoped

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
                "knowledge_scope": bundle.diagnostics.get("knowledge_scope", "auto"),
                "base_retrievers": bundle.diagnostics.get("base_retrievers", []),
                "effective_retrievers": bundle.diagnostics.get(
                    "effective_retrievers", bundle.retrievers
                ),
                "personal_documents_requested": bundle.diagnostics.get(
                    "personal_documents_requested", False
                ),
                "personal_documents_available": bundle.diagnostics.get(
                    "personal_documents_available", False
                ),
                "personal_documents_attempted": bundle.diagnostics.get(
                    "personal_documents_attempted", False
                ),
                "personal_documents_hit": bundle.diagnostics.get(
                    "personal_documents_hit", False
                ),
                "personal_documents_status": bundle.diagnostics.get(
                    "personal_documents_status", "not_requested"
                ),
                "personal_documents_used": bundle.diagnostics.get(
                    "personal_documents_used", False
                ),
                "retriever_status": bundle.diagnostics.get("retriever_status", {}),
                "coverage": bundle.coverage,
                "independent_source_count": bundle.independent_source_count,
                "fallback": bundle.fallback,
                "trace_id": bundle.trace_id,
                "evidence_assessment": bundle.diagnostics.get("evidence_assessment"),
                "personal_relevance": bundle.diagnostics.get("personal_relevance", []),
                "evidence_selection": bundle.diagnostics.get("evidence_selection", {}),
                "rescue_attempts": bundle.diagnostics.get("rescue_attempts", 0),
            },
        }
