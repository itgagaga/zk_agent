"""增强模式下个人资料的相关性评估与动态证据选择。

该模块只复用已有检索结果和结构化元数据，不调用 LLM、Embedding 或外部 API。
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from backend.config import settings
from backend.rag.contracts import (
    Evidence,
    EvidenceAssessment,
    EvidenceBundle,
    PersonalRelevanceAssessment,
    PersonalRelevanceLevel,
    SubQuestion,
)


_PERSONAL_MARKERS = (
    "我的",
    "个人",
    "我上传",
    "这份",
    "这篇",
    "根据我的",
    "结合我的",
)
_CONCEPT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("培养方案", ("培养方案", "教学进程", "课程安排")),
    ("课程", ("课程", "必修", "选修", "程序设计")),
    ("学分", ("学分", "学时")),
    ("学期", ("学期", "大一上", "大一下", "大二上", "大二下")),
    ("年级", ("大一", "大二", "大三", "大四", "本科生")),
    ("专业", ("信计", "信息与计算科学", "专业")),
    ("实践", ("实践", "实习", "毕业设计", "创新创业")),
    ("就业", ("就业", "岗位", "招聘", "职业")),
    ("新闻", ("新闻", "公告", "通知")),
    ("天气", ("天气", "气温", "下雨", "带伞")),
    ("路线", ("路线", "导航", "怎么去")),
)


@dataclass(frozen=True)
class _Candidate:
    evidence: Evidence
    subquestion_id: str
    level: PersonalRelevanceLevel | None
    relevance: float
    utility: float


class PersonalEvidencePolicy:
    """计算个人资料相关度，并按新增信息量选择回答上下文。"""

    def assess(
        self,
        bundle: EvidenceBundle,
        assessment: EvidenceAssessment | None = None,
    ) -> list[PersonalRelevanceAssessment]:
        subquestions = bundle.subquestions or [
            SubQuestion(id="q1", query=bundle.query, retrievers=[])
        ]
        grouped = self._group_personal(bundle.evidences)
        assessment_by_id = {
            item.id: item for item in (assessment.subquestions if assessment else [])
        }
        results: list[PersonalRelevanceAssessment] = []
        for subquestion in subquestions:
            candidates = grouped.get(subquestion.id, [])
            sub_assessment = assessment_by_id.get(subquestion.id)
            results.append(
                self._assess_subquestion(
                    subquestion,
                    candidates,
                    sub_assessment=sub_assessment,
                )
            )
        return results

    def select(
        self,
        bundle: EvidenceBundle,
        assessment: EvidenceAssessment | None = None,
    ) -> tuple[list[Evidence], list[PersonalRelevanceAssessment], dict[str, Any]]:
        """选择最终上下文；legacy 模式保持旧行为。"""
        relevance = self.assess(bundle, assessment)
        if (
            settings.rag_personal_priority_policy != "adaptive"
            or bundle.diagnostics.get("knowledge_scope") not in {"with_personal", "personal_only"}
        ):
            return bundle.evidences, relevance, {
                "policy": "legacy",
                "selection_duration_ms": 0.0,
                "context_chars": sum(self._evidence_size(item) for item in bundle.evidences),
            }

        level_by_subquestion = {item.subquestion_id: item.level for item in relevance}
        subquestion_by_evidence = {
            id(evidence): str(evidence.metadata.get("subquestion_id") or "q1")
            for evidence in bundle.evidences
        }
        candidates: list[_Candidate] = []
        for evidence in bundle.evidences:
            subquestion_id = subquestion_by_evidence[id(evidence)]
            level = level_by_subquestion.get(subquestion_id)
            if (
                evidence.retriever == "user_docs"
                and level == "none"
                and bundle.diagnostics.get("knowledge_scope") != "personal_only"
            ):
                continue
            if self._has_conflict(evidence, bundle.query) and evidence.retriever == "user_docs":
                continue
            relevance_score = self._relevance_score(evidence, level)
            candidates.append(
                _Candidate(
                    evidence=evidence,
                    subquestion_id=subquestion_id,
                    level=level,
                    relevance=relevance_score,
                    utility=0.0,
                )
            )

        selected: list[Evidence] = []
        selected_terms: list[set[str]] = []
        selected_subquestions: set[str] = set()
        context_chars = 0
        max_chars = settings.rag_answer_context_max_chars
        while candidates:
            scored: list[tuple[float, _Candidate, set[str]]] = []
            for candidate in candidates:
                terms = self._terms(self._evidence_text(candidate.evidence))
                novelty = self._novelty(terms, selected_terms)
                coverage_gain = 0.32 if candidate.subquestion_id not in selected_subquestions else 0.0
                personal_bonus = self._personal_priority(candidate.level, candidate.evidence)
                utility = (
                    candidate.relevance * 0.48
                    + novelty * 0.20
                    + coverage_gain
                    + personal_bonus
                )
                scored.append((utility, candidate, terms))
            scored.sort(key=lambda item: (-item[0], item[1].evidence.evidence_id))
            utility, candidate, terms = scored[0]
            if selected and utility < settings.rag_evidence_min_utility:
                break
            item_size = self._evidence_size(candidate.evidence)
            if selected and context_chars + item_size > max_chars:
                candidates.remove(candidate)
                continue
            selected.append(candidate.evidence)
            selected_terms.append(terms)
            selected_subquestions.add(candidate.subquestion_id)
            context_chars += item_size
            candidates.remove(candidate)

        selected_ids = {item.evidence_id for item in selected}
        for item in relevance:
            item.personal_selected_count = sum(
                1
                for evidence in selected
                if evidence.retriever == "user_docs"
                and str(evidence.metadata.get("subquestion_id") or "q1") == item.subquestion_id
            )
        diagnostics = {
            "policy": "adaptive",
            "context_chars": context_chars,
            "selected_count": len(selected),
            "selected_personal_count": sum(
                evidence.retriever == "user_docs" for evidence in selected
            ),
            "selected_public_count": sum(
                evidence.retriever not in {"user_docs"} for evidence in selected
            ),
            "discarded_count": len(bundle.evidences) - len(selected_ids),
        }
        return selected, relevance, diagnostics

    def _assess_subquestion(
        self,
        subquestion: SubQuestion,
        candidates: list[Evidence],
        *,
        sub_assessment: Any = None,
    ) -> PersonalRelevanceAssessment:
        if not candidates:
            return PersonalRelevanceAssessment(
                subquestion_id=subquestion.id,
                level="none",
                reason_code="no_personal_candidate",
            )

        query = subquestion.query
        query_concepts = self._concepts(query)
        direct_ids = set(getattr(sub_assessment, "directly_supported_ids", []) or [])
        best_matches = 0
        best_direct = False
        best_conflict = False
        matched_concepts: set[str] = set()
        for evidence in candidates:
            evidence_concepts = self._concepts(self._evidence_text(evidence))
            matches = query_concepts & evidence_concepts
            matched_concepts.update(matches)
            best_matches = max(best_matches, len(matches))
            best_direct = best_direct or evidence.evidence_id in direct_ids
            best_conflict = best_conflict or self._has_conflict(evidence, query)

        explicit = any(marker in query for marker in _PERSONAL_MARKERS)
        if best_conflict and not matched_concepts:
            level: PersonalRelevanceLevel = "none"
            reason = "personal_conflict"
        elif best_direct or (len(matched_concepts) >= 2 and self._query_is_personal_topic(query)):
            level = "high"
            reason = "direct_topic_coverage"
        elif matched_concepts or explicit:
            level = "medium"
            reason = "partial_topic_coverage"
        elif not query_concepts:
            # 查询过于宽泛时不能证明无关；保留为低相关候选，避免破坏文档问答。
            level = "low"
            reason = "generic_query"
        else:
            level = "none"
            reason = "no_topic_overlap"
        return PersonalRelevanceAssessment(
            subquestion_id=subquestion.id,
            level=level,
            personal_candidate_count=len(candidates),
            matched_concepts=sorted(matched_concepts),
            has_conflict=best_conflict,
            reason_code=reason,
        )

    @staticmethod
    def _group_personal(evidences: Iterable[Evidence]) -> dict[str, list[Evidence]]:
        grouped: dict[str, list[Evidence]] = {}
        for evidence in evidences:
            if evidence.retriever != "user_docs":
                continue
            subquestion_id = str(evidence.metadata.get("subquestion_id") or "q1")
            grouped.setdefault(subquestion_id, []).append(evidence)
        return grouped

    @classmethod
    def _concepts(cls, text: str) -> set[str]:
        normalized = str(text or "").lower()
        return {
            label
            for label, aliases in _CONCEPT_ALIASES
            if any(alias.lower() in normalized for alias in aliases)
        }

    @classmethod
    def _query_is_personal_topic(cls, query: str) -> bool:
        concepts = cls._concepts(query)
        return bool(concepts & {"培养方案", "课程", "学分", "学期", "年级", "专业", "实践"})

    @staticmethod
    def _evidence_text(evidence: Evidence) -> str:
        return f"{evidence.title}\n{evidence.snippet}\n{evidence.metadata}"

    @classmethod
    def _relevance_score(
        cls,
        evidence: Evidence,
        level: PersonalRelevanceLevel | None,
    ) -> float:
        rank = evidence.rank or evidence.dense_rank or evidence.lexical_rank or 20
        rank_score = 1.0 / (1.0 + max(rank - 1, 0) * 0.15)
        score = evidence.rerank_score
        if score is None:
            score = evidence.score
        return max(0.0, min(1.0, float(score) * 0.55 + rank_score * 0.45 + (0.1 if level == "high" else 0.0)))

    @staticmethod
    def _personal_priority(
        level: PersonalRelevanceLevel | None,
        evidence: Evidence,
    ) -> float:
        if evidence.retriever != "user_docs":
            return 0.08 if level in {"high", "medium"} else 0.0
        return {"high": 0.42, "medium": 0.16, "low": 0.0, "none": -1.0, None: 0.0}[level]

    @staticmethod
    def _terms(text: str) -> set[str]:
        normalized = re.sub(r"\s+", "", text.lower())
        terms = set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2}", normalized))
        for index in range(len(normalized) - 1):
            pair = normalized[index : index + 2]
            if all("\u4e00" <= char <= "\u9fff" for char in pair):
                terms.add(pair)
        return terms

    @classmethod
    def _novelty(cls, terms: set[str], selected_terms: list[set[str]]) -> float:
        if not terms or not selected_terms:
            return 1.0
        overlap = max(len(terms & previous) / max(len(terms), 1) for previous in selected_terms)
        return max(0.0, 1.0 - overlap)

    @staticmethod
    def _evidence_size(evidence: Evidence) -> int:
        return len(evidence.title) + len(evidence.snippet) + 180

    @staticmethod
    def _has_conflict(evidence: Evidence, query: str) -> bool:
        query_years = set(re.findall(r"20\d{2}", query or ""))
        text = PersonalEvidencePolicy._evidence_text(evidence)
        evidence_years = set(re.findall(r"20\d{2}", text))
        if query_years and evidence_years and not query_years & evidence_years:
            return True
        if "本科" in query and any(term in text for term in ("研究生", "硕士", "考研")) and "本科" not in text:
            return True
        return False
