"""使用 Reciprocal Rank Fusion 融合不同检索器的候选。"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Literal

from backend.rag.contracts import Evidence, EvidenceBundle


class EvidenceFusion:
    """将 dense、BM25 和工具结果转换到统一的排名量纲。"""

    def __init__(
        self,
        *,
        max_items: int = 12,
        rrf_k: int = 60,
        mode: Literal["legacy", "rrf"] = "rrf",
    ) -> None:
        self.max_items = max_items
        self.rrf_k = rrf_k
        self.mode = mode

    def fuse(
        self,
        query: str,
        evidences: Iterable[Evidence],
        *,
        retrievers: list[str],
        trace_id: str | None = None,
    ) -> EvidenceBundle:
        candidates = list(evidences)
        self._assign_missing_ranks(candidates)

        unique: dict[str, Evidence] = {}
        for evidence in candidates:
            evidence.fusion_score = (
                self._rrf_score(evidence) if self.mode == "rrf" else evidence.score
            )
            key = self._dedupe_key(evidence)
            previous = unique.get(key)
            if previous is None:
                unique[key] = evidence
            else:
                unique[key] = self._merge_duplicate(previous, evidence)
                unique[key].fusion_score = (
                    self._rrf_score(unique[key])
                    if self.mode == "rrf"
                    else unique[key].score
                )

        selected = sorted(
            unique.values(),
            key=lambda item: (
                -item.fusion_score,
                -(item.rerank_score if item.rerank_score is not None else float("-inf")),
                -item.score,
                item.retriever,
                item.evidence_id,
            ),
        )[: self.max_items]
        independent = len({item.retriever for item in selected})
        expected = len(set(retrievers))
        coverage = independent / expected if expected else 0.0
        return EvidenceBundle(
            query=query,
            evidences=selected,
            retrievers=sorted({item.retriever for item in selected}),
            coverage=round(min(coverage, 1.0), 4),
            independent_source_count=independent,
            fallback=not selected,
            trace_id=trace_id,
            diagnostics={"fusion": self.mode, "rrf_k": self.rrf_k},
        )

    def _rrf_score(self, evidence: Evidence) -> float:
        ranks: list[int] = []
        for rank in (evidence.dense_rank, evidence.lexical_rank, evidence.tool_rank):
            if rank is not None and int(rank) > 0:
                ranks.append(int(rank))
        if not ranks and evidence.rank is not None and int(evidence.rank) > 0:
            ranks.append(int(evidence.rank))
        return sum(1.0 / (self.rrf_k + rank) for rank in ranks)

    @staticmethod
    def _dedupe_key(evidence: Evidence) -> str:
        if evidence.kind in {"rag", "document"}:
            doc_id = evidence.doc_id or evidence.metadata.get("doc_id")
            parent_id = evidence.metadata.get("parent_id")
            if doc_id and parent_id:
                return f"document:{doc_id}:{parent_id}"
            if doc_id:
                return f"document:{doc_id}:{evidence.chunk_id or ''}"
        return f"{evidence.retriever}:{evidence.evidence_id}"

    @staticmethod
    def _merge_duplicate(first: Evidence, second: Evidence) -> Evidence:
        winner = max(
            (first, second),
            key=lambda item: (
                item.fusion_score,
                item.rerank_score if item.rerank_score is not None else float("-inf"),
                item.score,
            ),
        )
        merged = winner.model_copy(deep=True)
        for field in ("dense_rank", "lexical_rank", "tool_rank"):
            values = [getattr(first, field), getattr(second, field)]
            values = [int(value) for value in values if value is not None and int(value) > 0]
            if values:
                setattr(merged, field, min(values))
        return merged

    def _assign_missing_ranks(self, evidences: list[Evidence]) -> None:
        """为旧调用方没有传 rank 的证据提供稳定的兼容排名。"""
        groups: dict[str, list[Evidence]] = defaultdict(list)
        for evidence in evidences:
            groups[evidence.retriever].append(evidence)
        for group in groups.values():
            group.sort(key=lambda item: (-item.score, item.evidence_id))
            for index, evidence in enumerate(group, start=1):
                if evidence.dense_rank is None and evidence.lexical_rank is None and evidence.tool_rank is None and evidence.rank is None:
                    if evidence.kind in {"tool", "api"}:
                        evidence.tool_rank = index
                    else:
                        evidence.dense_rank = index
                elif evidence.kind in {"tool", "api"} and evidence.tool_rank is None and evidence.rank is not None:
                    evidence.tool_rank = int(evidence.rank)
