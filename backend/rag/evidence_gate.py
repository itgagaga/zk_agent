"""按子问题判断证据是否支持回答，避免把“有候选”误判为可回答。"""
from __future__ import annotations

import inspect
import re
from collections import defaultdict
from typing import Any, Callable, Iterable

from backend.config import settings
from backend.rag.contracts import (
    Evidence,
    EvidenceAssessment,
    EvidenceBundle,
    EvidenceStatus,
    SubquestionAssessment,
)

__all__ = ["EvidenceAssessment", "EvidenceGate"]


EVIDENCE_JUDGE_SYSTEM_PROMPT = """你是校园问答系统的 Evidence Judge。
你只能判断给定证据是否支持每个子问题，不得生成答案，不得补充证据中没有的事实。
请输出符合 EvidenceAssessment 的结构化结果：区分 supported、partial、unsupported，
列出直接支持的 evidence_id、未覆盖信息、年份/适用对象/文档类型冲突，以及是否建议一次改写重试。
temperature 必须为 0。"""


class EvidenceGate:
    """Evidence Judge 的确定性预检查与可选结构化 Judge 适配层。"""

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
    _TOPIC_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("校园卡", ("校园卡", "一卡通")),
        ("挂失补办", ("丢", "遗失", "挂失", "补办")),
        ("材料", ("材料", "所需材料")),
        ("地点", ("地点", "地址", "位置")),
        ("网络", ("网络", "报障", "报修", "故障")),
        ("海珠校区", ("海珠校区",)),
        ("白云校区", ("白云校区",)),
        ("培养方案", ("培养方案", "课程安排")),
        ("专业目录", ("专业目录", "专业代码")),
        ("招聘", ("招聘会", "双选会", "宣讲会", "招聘")),
    )
    _QUESTION_FRAMES = (
        "主要讲了什么", "讲了什么", "介绍了什么", "在哪里", "在哪",
        "有哪些", "有什么", "是什么", "请问", "帮我", "一下", "吗", "呢",
        "分别是什么", "是多少", "如何", "怎么办",
    )

    def __init__(
        self,
        *,
        min_fusion_score: float = 0.01,
        judge: Callable[..., Any] | None = None,
    ) -> None:
        self.min_fusion_score = min_fusion_score
        # 可注入同步/异步结构化 Judge；不可用时始终走保守确定性判断。
        self.judge = judge
        self._structured_llm: Any = None
        if judge is None:
            self._init_llm()

    def _init_llm(self) -> None:
        if not settings.rag_evidence_judge_enabled or not settings.deepseek_api_key:
            return
        try:
            from langchain_deepseek import ChatDeepSeek

            llm = ChatDeepSeek(
                model=settings.rag_evidence_judge_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=0.0,
                max_tokens=1200,
            )
            self._structured_llm = llm.with_structured_output(EvidenceAssessment)
        except Exception as exc:  # pragma: no cover - optional dependency/config
            print(f"[EvidenceGate] Structured Judge 初始化失败，将使用确定性预检查: {exc}")

    def assess(self, bundle: EvidenceBundle) -> EvidenceAssessment:
        """执行不依赖 LLM 的确定性预检查。"""
        assignments = self._assign_evidence(bundle)
        subquestions = self._subquestions(bundle, assignments)
        retrieval_failures = sorted(
            set(bundle.diagnostics.get("retrieval_failures", []))
            | {
                evidence.retriever
                for evidence in bundle.evidences
                if self._error_message(evidence)
            }
        )

        results: list[SubquestionAssessment] = []
        supported_ids: list[str] = []
        partial_ids: list[str] = []
        missing_information: list[str] = []
        conflicts: list[str] = []
        matched_concepts: list[str] = []
        missing_concepts: list[str] = []

        for subquestion_id, query in subquestions:
            candidates = assignments.get(subquestion_id, [])
            result = self._assess_subquestion(subquestion_id, query, candidates)
            results.append(result)
            if result.status == "supported":
                supported_ids.extend(result.directly_supported_ids)
            else:
                partial_ids.extend(result.evidence_ids)
            missing_information.extend(result.missing_information)
            conflicts.extend(result.conflicts)
            matched_concepts.extend(
                concept for concept in self._requirements(query)
                if any(self._matches(concept, evidence) for evidence in candidates)
            )
            requirements = self._requirements(query)
            missing_concepts.extend(
                concept for concept in requirements
                if not any(self._matches(concept, evidence) for evidence in assignments.get(subquestion_id, []))
            )

        total = len(results)
        supported_count = sum(result.status == "supported" for result in results)
        partial_count = sum(result.status == "partial" for result in results)
        if total and supported_count == total:
            status: EvidenceStatus = "supported"
        elif supported_count or partial_count:
            status = "partial"
        else:
            status = "unsupported"
        coverage = round(
            sum(result.coverage for result in results) / total if total else 0.0,
            4,
        )
        if retrieval_failures and status == "supported":
            # 有明确失败的工具时不能把整体包装成完整支持。
            status = "partial"
        if not bundle.evidences:
            status = "unsupported"

        reason = self._overall_reason(status, results, retrieval_failures)
        retry_query = self._build_retry_query(bundle.query, missing_information, conflicts)
        should_retry = bool(bundle.evidences) and status != "supported" and not retrieval_failures and bool(retry_query)
        if not should_retry:
            retry_query = None
        assessment = EvidenceAssessment(
            status=status,
            coverage=coverage,
            subquestions=results,
            supported_evidence_ids=list(dict.fromkeys(supported_ids)),
            partial_evidence_ids=list(dict.fromkeys(partial_ids)),
            missing_information=list(dict.fromkeys(missing_information)),
            conflicts=list(dict.fromkeys(conflicts)),
            retrieval_failures=retrieval_failures,
            retry_recommended=should_retry,
            should_retry=should_retry,
            retry_query=retry_query,
            matched_concepts=list(dict.fromkeys(matched_concepts)),
            missing_concepts=list(dict.fromkeys(missing_concepts)),
            reason=reason,
        )
        return assessment

    async def assess_async(self, bundle: EvidenceBundle) -> EvidenceAssessment:
        """执行确定性预检查，并可选调用外部 Structured Evidence Judge。"""
        deterministic = self.assess(bundle)
        judge = self.judge
        if judge is None and self._structured_llm is not None:
            try:
                from langchain_core.messages import HumanMessage, SystemMessage

                output = await self._structured_llm.ainvoke([
                    SystemMessage(content=EVIDENCE_JUDGE_SYSTEM_PROMPT),
                    HumanMessage(content=str(self._judge_payload(bundle))),
                ])
                if isinstance(output, EvidenceAssessment):
                    return self._constrain_judge_output(output, deterministic)
                if isinstance(output, dict):
                    return self._constrain_judge_output(
                        EvidenceAssessment.model_validate(output), deterministic
                    )
            except Exception as exc:  # pragma: no cover - external LLM failure
                deterministic.reason = f"Structured Evidence Judge 不可用，采用保守预检查：{type(exc).__name__}"
            return deterministic
        if judge is None:
            return deterministic
        try:
            payload = self._judge_payload(bundle)
            output = judge(payload)
            if inspect.isawaitable(output):
                output = await output
            if isinstance(output, EvidenceAssessment):
                return self._constrain_judge_output(output, deterministic)
            if isinstance(output, dict):
                return self._constrain_judge_output(
                    EvidenceAssessment.model_validate(output), deterministic
                )
        except Exception as exc:  # pragma: no cover - external Judge failure
            deterministic.reason = f"Structured Evidence Judge 不可用，采用保守预检查：{type(exc).__name__}"
        return deterministic

    @staticmethod
    def _constrain_judge_output(
        judged: EvidenceAssessment,
        deterministic: EvidenceAssessment,
    ) -> EvidenceAssessment:
        """禁止 Judge 把确定性硬失败升级成完整支持。"""
        if deterministic.status == "unsupported" and not deterministic.supported_evidence_ids:
            return deterministic
        return judged

    def rank(self, query: str, evidences: Iterable[Evidence]) -> list[Evidence]:
        """按子问题相关性与 RRF 结果重排，不再跨来源比较原始分数。"""
        requirements = self._requirements(query)
        ranked: list[tuple[float, Evidence]] = []
        for evidence in evidences:
            matched = sum(1 for concept in requirements if self._matches(concept, evidence))
            contradiction = len(self._conflicts(query, evidence))
            base = evidence.fusion_score if evidence.fusion_score > 0 else evidence.score
            relevance = float(base) + matched * 0.1 - contradiction * 0.2
            ranked.append((relevance, evidence))
        ranked.sort(key=lambda item: (-item[0], item[1].evidence_id))
        return [evidence for _, evidence in ranked]

    def _assess_subquestion(
        self,
        subquestion_id: str,
        query: str,
        candidates: list[Evidence],
    ) -> SubquestionAssessment:
        requirements = self._requirements(query)
        if not candidates:
            return SubquestionAssessment(
                id=subquestion_id,
                query=query,
                status="unsupported",
                missing_information=["该子问题没有分配到检索证据"],
                reason="没有分配到该子问题的证据",
            )

        valid_candidates = [evidence for evidence in candidates if not self._error_message(evidence)]
        if not valid_candidates:
            return SubquestionAssessment(
                id=subquestion_id,
                query=query,
                status="unsupported",
                evidence_ids=[evidence.evidence_id for evidence in candidates],
                missing_information=["检索器返回错误，无法确认该子问题"],
                reason="检索器明确返回错误",
            )

        ranked_candidates = [evidence for evidence in valid_candidates if self._has_usable_score(evidence)]
        if not ranked_candidates:
            return SubquestionAssessment(
                id=subquestion_id,
                query=query,
                status="unsupported",
                evidence_ids=[evidence.evidence_id for evidence in candidates],
                missing_information=["候选证据的 RRF/reranker 分数低于最低门槛"],
                reason="证据排序分数不足",
            )

        matched = [
            concept for concept in requirements
            if any(self._matches(concept, evidence) for evidence in ranked_candidates)
        ]
        missing = [concept for concept in requirements if concept not in matched]
        conflict_list = list(dict.fromkeys(
            conflict for evidence in ranked_candidates for conflict in self._conflicts(query, evidence)
        ))
        critical_missing = {
            label for label in missing
            if label in {"本科", "研究生", "章程", "简章", "海珠校区", "白云校区", "2026"}
        }
        directly_supported = [
            evidence.evidence_id
            for evidence in ranked_candidates
            if self._matches_enough(requirements, evidence) and not self._conflicts(query, evidence)
        ]
        coverage = len(matched) / len(requirements) if requirements else 0.0
        independent_sources = len({self._source_key(evidence) for evidence in ranked_candidates})

        if not matched and requirements:
            status: EvidenceStatus = "unsupported"
        elif coverage >= 0.8 and directly_supported and not critical_missing:
            status = "supported"
        else:
            status = "partial"
        missing_information = [f"未覆盖：{item}" for item in missing]
        if conflict_list:
            missing_information.append("存在适用对象或文档类型冲突")
        return SubquestionAssessment(
            id=subquestion_id,
            query=query,
            status=status,
            coverage=round(coverage, 4),
            evidence_ids=[evidence.evidence_id for evidence in candidates],
            directly_supported_ids=directly_supported,
            missing_information=missing_information,
            conflicts=conflict_list,
            independent_source_count=independent_sources,
            reason=self._subquestion_reason(status, conflict_list),
        )

    def _has_usable_score(self, evidence: Evidence) -> bool:
        if evidence.rerank_score is not None:
            return evidence.rerank_score >= 0.1
        # 未经过 RRF 的旧 API/测试证据仍可按原始分数进入保守检查。
        if evidence.fusion_score <= 0:
            return evidence.score > 0
        return evidence.fusion_score >= self.min_fusion_score

    def _requirements(self, query: str) -> dict[str, tuple[str, ...]]:
        normalized = re.sub(r"[？?！!。；;，,、\s]+", "", query or "").lower()
        for frame in self._QUESTION_FRAMES:
            normalized = normalized.replace(frame, "")
        requirements: dict[str, tuple[str, ...]] = {}
        for label, aliases in (*self._ALIASES, *self._TOPIC_ALIASES):
            if any(alias.lower() in normalized for alias in aliases):
                requirements[label] = aliases
        # 年份和明确的数字实体必须被同一条证据覆盖，避免跨年度拼接。
        for year in re.findall(r"20\d{2}", normalized):
            requirements[year] = (year,)
        return requirements

    @staticmethod
    def _matches(label: str, evidence: Evidence) -> bool:
        text = f"{evidence.title}\n{evidence.snippet}\n{evidence.metadata}".lower()
        aliases = {
            "本科": ("本科", "普通高考", "高考"),
            "研究生": ("研究生", "硕士", "考研"),
            "章程": ("招生章程", "章程"),
            "简章": ("招生简章", "简章"),
            "招生": ("招生", "录取"),
            "申请表": ("申请表", "表格", "表"),
            "联系方式": ("电话", "联系方式", "联系"),
            "路线": ("路线", "怎么去", "导航"),
            "天气": ("天气", "气温", "下雨"),
            "校区": ("校区", "校园地址", "学校地址"),
            "校园卡": ("校园卡", "一卡通"),
            "挂失补办": ("丢", "遗失", "挂失", "补办"),
            "材料": ("材料", "所需材料"),
            "地点": ("地点", "地址", "位置"),
            "网络": ("网络", "报障", "报修", "故障"),
            "海珠校区": ("海珠校区",),
            "白云校区": ("白云校区",),
            "培养方案": ("培养方案", "课程安排"),
            "专业目录": ("专业目录", "专业代码"),
            "招聘": ("招聘会", "双选会", "宣讲会", "招聘"),
        }.get(label, (label,))
        return any(alias.lower() in text for alias in aliases)

    def _matches_enough(self, requirements: dict[str, tuple[str, ...]], evidence: Evidence) -> bool:
        if not requirements:
            return False
        return sum(self._matches(label, evidence) for label in requirements) / len(requirements) >= 0.8

    def _conflicts(self, query: str, evidence: Evidence) -> list[str]:
        text = f"{evidence.title}\n{evidence.snippet}".lower()
        conflicts: list[str] = []
        if "本科" in query and any(term in text for term in ("研究生", "硕士", "考研")) and not any(term in text for term in ("本科", "普通高考")):
            conflicts.append("问题要求本科资料，但证据属于研究生/硕士范围")
        if any(term in query for term in ("研究生", "硕士", "考研")) and "本科" in text and not any(term in text for term in ("研究生", "硕士")):
            conflicts.append("问题要求研究生资料，但证据属于本科范围")
        if "章程" in query and "简章" in evidence.title and "章程" not in evidence.title:
            conflicts.append("问题要求招生章程，但证据标题是招生简章")
        return conflicts

    @staticmethod
    def _source_key(evidence: Evidence) -> str:
        return evidence.doc_id or evidence.metadata.get("doc_id") or evidence.retriever

    @staticmethod
    def _error_message(evidence: Evidence) -> str | None:
        for payload in (evidence.raw, evidence.metadata):
            if payload.get("error"):
                return str(payload["error"])
            if str(payload.get("status", "")).lower() in {"error", "failed"}:
                return str(payload.get("status"))
        return None

    @staticmethod
    def _assign_evidence(bundle: EvidenceBundle) -> dict[str, list[Evidence]]:
        grouped: dict[str, list[Evidence]] = defaultdict(list)
        ids = {evidence.metadata.get("subquestion_id") for evidence in bundle.evidences}
        ids.discard(None)
        if not ids:
            grouped["q1"].extend(bundle.evidences)
            return grouped
        default_id = bundle.subquestions[0].id if bundle.subquestions else sorted(ids)[0]
        for evidence in bundle.evidences:
            subquestion_id = evidence.metadata.get("subquestion_id") or default_id
            grouped[str(subquestion_id)].append(evidence)
        return grouped

    @staticmethod
    def _subquestions(
        bundle: EvidenceBundle,
        assignments: dict[str, list[Evidence]],
    ) -> list[tuple[str, str]]:
        if bundle.subquestions:
            return [(subquestion.id, subquestion.query) for subquestion in bundle.subquestions]
        if assignments:
            return [(subquestion_id, bundle.query) for subquestion_id in assignments]
        return [("q1", bundle.query)]

    @staticmethod
    def _overall_reason(
        status: EvidenceStatus,
        results: list[SubquestionAssessment],
        retrieval_failures: list[str],
    ) -> str:
        if retrieval_failures:
            return f"部分检索器失败：{', '.join(retrieval_failures)}"
        if status == "supported":
            return "每个子问题都有相互匹配且无明显冲突的证据"
        if status == "partial":
            return "仅部分子问题或部分信息得到证据支持，不能当作完整回答"
        if any(result.missing_information for result in results):
            return "没有证据充分支持当前问题"
        return "没有检索到可引用证据"

    @staticmethod
    def _build_retry_query(
        query: str,
        missing_information: list[str],
        conflicts: list[str],
    ) -> str:
        missing = [item.replace("未覆盖：", "").strip() for item in missing_information]
        missing = [item for item in missing if item and not item.startswith("该子问题")]
        hints = list(dict.fromkeys(missing[:5]))
        if conflicts:
            hints.append("排除冲突适用对象或文档类型")
        if not hints:
            return ""
        return f"{query}；重点核实：{'、'.join(hints)}"

    @staticmethod
    def _subquestion_reason(status: EvidenceStatus, conflicts: list[str]) -> str:
        if conflicts:
            return "证据存在适用范围或文档类型冲突"
        if status == "supported":
            return "证据覆盖该子问题的主要要求"
        if status == "partial":
            return "证据只覆盖该子问题的一部分要求"
        return "没有证据覆盖该子问题的核心要求"

    @staticmethod
    def _judge_payload(bundle: EvidenceBundle) -> dict[str, Any]:
        return {
            "subquestions": [
                {"id": item.id, "query": item.query}
                for item in bundle.subquestions
            ] or [{"id": "q1", "query": bundle.query}],
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "title": item.title,
                    "snippet": item.snippet,
                    "source": item.retriever,
                    "date": item.metadata.get("publish_date"),
                }
                for item in bundle.evidences
            ],
        }
