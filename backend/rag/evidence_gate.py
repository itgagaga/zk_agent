"""判断检索证据是否足以支持回答，避免把“有候选”误判为“可回答”。"""
from __future__ import annotations

import re
from typing import Iterable, Literal

from pydantic import BaseModel, Field

from backend.rag.contracts import Evidence, EvidenceBundle


class EvidenceAssessment(BaseModel):
    status: Literal["sufficient", "needs_more", "unsupported"]
    coverage: float = 0.0
    matched_concepts: list[str] = Field(default_factory=list)
    missing_concepts: list[str] = Field(default_factory=list)
    reason: str = ""


class EvidenceGate:
    """查询概念覆盖门控；不比较不同检索器的全局优先级。"""

    _ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("本科", ("本科", "普通高考", "高考")),
        ("研究生", ("研究生", "硕士", "考研")),
        ("章程", ("招生章程", "章程")),
        ("简章", ("招生简章", "简章")),
        ("招生", ("招生", "录取")),
        ("申请表", ("申请表", "表格", "表")),
        ("联系方式", ("电话", "联系方式", "联系")),
        ("路线", ("路线", "怎么去", "导航")),
        ("天气", ("天气", "气温", "下雨")),
        ("校区", ("校区", "校园地址", "学校地址")),
    )
    _QUESTION_FRAMES = (
        "主要讲了什么", "讲了什么", "介绍了什么", "在哪里", "在哪",
        "有哪些", "有什么", "是什么", "请问", "帮我", "一下", "吗", "呢",
    )

    def assess(self, bundle: EvidenceBundle) -> EvidenceAssessment:
        concepts = self._concept_groups(bundle.query)
        if not bundle.evidences:
            return EvidenceAssessment(
                status="unsupported",
                reason="没有检索到可引用证据",
                missing_concepts=list(concepts),
            )
        if not concepts:
            return EvidenceAssessment(
                status="sufficient",
                coverage=1.0,
                reason="问题未包含可稳定识别的领域概念，保留已有证据交由生成器判断",
            )

        evidence_text = "\n".join(
            f"{e.title}\n{e.snippet}" for e in bundle.evidences
        ).lower()
        matched: list[str] = []
        missing: list[str] = []
        for label, aliases in concepts.items():
            if any(alias.lower() in evidence_text for alias in aliases):
                matched.append(label)
            else:
                missing.append(label)
        coverage = len(matched) / len(concepts)
        critical_missing = set(missing) & {"本科", "研究生", "章程", "简章"}
        if not missing or (coverage >= 0.75 and not critical_missing):
            status: Literal["sufficient", "needs_more", "unsupported"] = "sufficient"
            reason = "证据覆盖问题核心概念"
        else:
            status = "needs_more"
            reason = "已有候选但缺少核心概念覆盖，应该执行补检索"
        return EvidenceAssessment(
            status=status,
            coverage=round(coverage, 4),
            matched_concepts=matched,
            missing_concepts=missing,
            reason=reason,
        )

    def rank(self, query: str, evidences: Iterable[Evidence]) -> list[Evidence]:
        """按概念支持度重排，不改写原始检索分数。"""
        concepts = self._concept_groups(query)
        ranked: list[tuple[float, Evidence]] = []
        for evidence in evidences:
            text = f"{evidence.title}\n{evidence.snippet}".lower()
            matched = sum(
                1 for aliases in concepts.values()
                if any(alias.lower() in text for alias in aliases)
            )
            contradiction = 0.0
            if "本科" in concepts and any(term in text for term in ("研究生", "硕士")):
                contradiction += 2.0
            if "章程" in concepts and "简章" in evidence.title and "章程" not in evidence.title:
                contradiction += 2.0
            if (
                "校区" in concepts
                and not any(term in query for term in ("电话", "网络", "报障", "联系", "天气", "路线"))
                and any(
                marker in evidence.title for marker in ("学校概况", "学校简介", "校园概况")
                )
            ):
                matched += 2
            relevance = float(evidence.score or 0.0) + matched * 2.0 - contradiction
            ranked.append((relevance, evidence))
        ranked.sort(key=lambda item: (-item[0], item[1].evidence_id))
        return [evidence for _, evidence in ranked]

    def _concept_groups(self, query: str) -> dict[str, tuple[str, ...]]:
        normalized = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", query).lower()
        for frame in self._QUESTION_FRAMES:
            normalized = normalized.replace(frame, "")
        groups: dict[str, tuple[str, ...]] = {}
        for label, aliases in self._ALIASES:
            if any(alias.lower() in normalized for alias in aliases):
                groups[label] = aliases
        return groups
