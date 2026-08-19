"""对不同检索器的候选做去重、校准和多样性融合。"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from backend.rag.contracts import Evidence, EvidenceBundle


class EvidenceFusion:
    def __init__(self, *, max_items: int = 12) -> None:
        self.max_items = max_items

    def fuse(
        self,
        query: str,
        evidences: Iterable[Evidence],
        *,
        retrievers: list[str],
        trace_id: str | None = None,
    ) -> EvidenceBundle:
        unique: dict[str, Evidence] = {}
        for evidence in evidences:
            previous = unique.get(evidence.evidence_id)
            if previous is None or evidence.score > previous.score:
                unique[evidence.evidence_id] = evidence

        groups: dict[str, list[Evidence]] = defaultdict(list)
        for evidence in unique.values():
            groups[evidence.retriever].append(evidence)
        for group in groups.values():
            group.sort(key=lambda item: (-item.score, item.evidence_id))

        selected: list[Evidence] = []
        # Round-robin gives a second source a chance without hard-coding a
        # global priority between RAG, tools, and APIs.
        while len(selected) < self.max_items and groups:
            progressed = False
            for retriever in sorted(list(groups)):
                bucket = groups[retriever]
                if not bucket:
                    groups.pop(retriever, None)
                    continue
                selected.append(bucket.pop(0))
                progressed = True
                if len(selected) >= self.max_items:
                    break
            if not progressed:
                break
        selected.sort(key=lambda item: (-item.score, item.retriever, item.evidence_id))
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
        )
