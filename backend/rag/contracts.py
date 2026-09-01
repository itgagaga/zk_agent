"""检索与证据融合的稳定数据契约。

各检索器可以保留自己的原始字段，但进入答案生成前统一转换为
``Evidence``。这样排序、去重、引用和前端元数据不再依赖某个 Agent 的
内部字典结构。
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr


EvidenceKind = Literal["rag", "document", "tool", "api"]
EvidenceStatus = Literal["supported", "partial", "unsupported"]
KnowledgeScope = Literal["auto", "with_personal", "personal_only"]
PersonalRelevanceLevel = Literal["high", "medium", "low", "none"]

# Planner 输出的检索器白名单。LLM 只能从这里选择，实际调用仍由服务端映射。
RetrievalTarget = Literal[
    "campus_rag",
    "shared_docs",
    "user_docs",
    "download_search",
    "contact_search",
    "service_link_search",
    "major_search",
    "job_search",
    "news_search",
    "weather_search",
    "map_route",
    "academic_search",
]


class SubQuestion(BaseModel):
    """一个可独立检索和验收的子问题。"""

    id: str
    query: str
    intent: str = "general"
    retrievers: list[RetrievalTarget] = Field(default_factory=list)
    entities: dict[str, str] = Field(default_factory=dict)
    filters: dict[str, str | int | bool] = Field(default_factory=dict)
    requires_private_context: bool = False


class RetrievalPlan(BaseModel, Coroutine[Any, Any, "RetrievalPlan"]):
    """Hybrid Query Planner 的稳定输出契约。"""

    original_query: str
    standalone_query: str
    language: str = "zh"
    subquestions: list[SubQuestion] = Field(default_factory=list)
    knowledge_scope: KnowledgeScope = "auto"
    base_retrievers: list[RetrievalTarget] = Field(default_factory=list)
    retrievers: list[RetrievalTarget] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    used_history: bool = False
    planner_source: Literal["llm", "rule_fallback"] = "rule_fallback"
    planner_reason: str = ""
    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    _deferred: Callable[[], Awaitable["RetrievalPlan"]] | None = PrivateAttr(default=None)
    _coroutine: Coroutine[Any, Any, "RetrievalPlan"] | None = PrivateAttr(default=None)

    # 旧调用方在迁移期间仍使用这两个名称；它们不再是独立状态。
    @property
    def query(self) -> str:
        return self.original_query

    @property
    def normalized_query(self) -> str:
        return self.standalone_query

    @property
    def allow_fallback(self) -> bool:
        return True

    def __await__(self):
        return self._get_coroutine().__await__()

    async def _resolve(self) -> "RetrievalPlan":
        if self._deferred is not None:
            deferred, self._deferred = self._deferred, None
            return await deferred()
        return self

    def _get_coroutine(self) -> Coroutine[Any, Any, "RetrievalPlan"]:
        if self._coroutine is None:
            self._coroutine = self._resolve()
        return self._coroutine

    def send(self, value: Any) -> Any:
        return self._get_coroutine().send(value)

    def throw(self, *args: Any) -> Any:
        return self._get_coroutine().throw(*args)

    def close(self) -> None:
        self._get_coroutine().close()


class SubquestionAssessment(BaseModel):
    """单个子问题的证据判断结果。"""

    id: str
    query: str
    status: EvidenceStatus
    coverage: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)
    directly_supported_ids: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    independent_source_count: int = 0
    reason: str = ""


class PersonalRelevanceAssessment(BaseModel):
    """个人资料对单个子问题的相关性诊断，不包含私有正文。"""

    subquestion_id: str
    level: PersonalRelevanceLevel
    personal_candidate_count: int = 0
    personal_selected_count: int = 0
    matched_concepts: list[str] = Field(default_factory=list)
    has_conflict: bool = False
    reason_code: str = "no_personal_evidence"


class EvidenceAssessment(BaseModel):
    """Evidence Judge 的结构化输出；只描述证据，不生成答案。"""

    status: EvidenceStatus
    coverage: float = 0.0
    subquestions: list[SubquestionAssessment] = Field(default_factory=list)
    supported_evidence_ids: list[str] = Field(default_factory=list)
    partial_evidence_ids: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    retrieval_failures: list[str] = Field(default_factory=list)
    retry_recommended: bool = False
    should_retry: bool = False
    retry_query: str | None = None
    matched_concepts: list[str] = Field(default_factory=list)
    missing_concepts: list[str] = Field(default_factory=list)
    reason: str = ""


class Evidence(BaseModel):
    """单条可引用证据。"""

    evidence_id: str
    kind: EvidenceKind
    retriever: str
    title: str = ""
    snippet: str = ""
    url: str = ""
    source_page_url: str = ""
    file_url: str = ""
    score: float = 0.0
    rank: int | None = None
    dense_rank: int | None = None
    lexical_rank: int | None = None
    tool_rank: int | None = None
    rerank_score: float | None = None
    fusion_score: float = 0.0
    doc_id: str | None = None
    chunk_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_rag_hit(cls, hit: dict[str, Any], *, retriever: str = "campus_rag") -> "Evidence":
        meta = dict(hit.get("metadata") or {})
        chunk_id = hit.get("chunk_id") or meta.get("chunk_id")
        doc_id = hit.get("doc_id") or meta.get("doc_id")
        evidence_id = str(chunk_id or doc_id or hit.get("url") or hit.get("title") or id(hit))
        retrieval_source = str(hit.get("retrieval_source") or "")
        dense_rank = hit.get("dense_rank")
        lexical_rank = hit.get("lexical_rank")
        if retrieval_source == "dense" and dense_rank is None:
            dense_rank = hit.get("rank")
        if retrieval_source == "lexical" and lexical_rank is None:
            lexical_rank = hit.get("rank")
        return cls(
            evidence_id=evidence_id,
            kind="document" if retriever == "user_docs" or meta.get("user_id") is not None else "rag",
            retriever=retriever,
            title=str(hit.get("title") or meta.get("title") or ""),
            snippet=str(hit.get("snippet") or ""),
            url=str(hit.get("url") or meta.get("source_url") or ""),
            source_page_url=str(hit.get("source_page_url") or ""),
            score=float(hit.get("score") or 0.0),
            rank=hit.get("rank"),
            dense_rank=dense_rank,
            lexical_rank=lexical_rank,
            rerank_score=hit.get("rerank_score"),
            doc_id=str(doc_id) if doc_id is not None else None,
            chunk_id=str(chunk_id) if chunk_id is not None else None,
            metadata=meta,
            raw=dict(hit),
        )

    @classmethod
    def from_tool_item(cls, item: dict[str, Any], *, tool: str) -> "Evidence":
        title = str(item.get("title") or item.get("name") or "")
        url = str(item.get("url") or item.get("source_page_url") or "")
        file_url = str(item.get("file_url") or "")
        stable = (
            item.get("evidence_id")
            or item.get("id")
            or file_url
            or url
            or f"{title}|{item.get('phone', '')}|{item.get('address', '')}"
        )
        return cls(
            evidence_id=f"{tool}:{stable}",
            kind="api" if tool in {"map_route", "weather_search"} else "tool",
            retriever=tool,
            title=title,
            snippet=str(
                item.get("snippet")
                or item.get("summary")
                or item.get("service_scope")
                or item.get("description")
                or ""
            ),
            url=url,
            source_page_url=str(item.get("source_page_url") or ""),
            file_url=file_url,
            score=float(item.get("score") or 0.0),
            rank=item.get("rank"),
            tool_rank=item.get("tool_rank") or item.get("rank"),
            rerank_score=item.get("rerank_score"),
            metadata=dict(item.get("metadata") or {}),
            raw=dict(item),
        )

    def to_source_dict(self) -> dict[str, Any]:
        """转换为现有 AnswerGenerator/frontend 使用的来源字段。"""
        return {
            "title": self.title,
            "department": self.metadata.get("department"),
            "url": self.file_url or self.url or self.source_page_url,
            "publish_date": self.metadata.get("publish_date"),
            "snippet": self.snippet,
            "evidence_id": self.evidence_id,
            "retriever": self.retriever,
            "score": self.score,
            "fusion_score": self.fusion_score,
            "dense_rank": self.dense_rank,
            "lexical_rank": self.lexical_rank,
            "tool_rank": self.tool_rank,
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
        }


class EvidenceBundle(BaseModel):
    """一次查询的规划、检索和融合结果。"""

    query: str
    evidences: list[Evidence] = Field(default_factory=list)
    subquestions: list[SubQuestion] = Field(default_factory=list)
    retrievers: list[str] = Field(default_factory=list)
    coverage: float = 0.0
    independent_source_count: int = 0
    fallback: bool = False
    trace_id: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    def sources(self) -> list[dict[str, Any]]:
        return [e.to_source_dict() for e in self.evidences]
