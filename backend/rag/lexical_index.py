"""中文 BM25 词法索引。

索引只负责词法召回和可诊断分数，不与向量 cosine 分数直接相加。
标题、章节和结构化来源字段通过字段权重参与 BM25，避免把常见问句词
或字符滑窗当成业务相关性。
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable


try:
    import jieba
except ImportError:  # pragma: no cover - exercised only before optional install
    jieba = None


_TOKEN_PATTERN = re.compile(r"[A-Za-z]+(?:[-_][A-Za-z0-9]+)*|\d+(?:\.\d+)?|[\u4e00-\u9fff]")
_DOMAIN_TERMS = tuple(sorted({
    "仲恺农业工程学院", "白云校区", "海珠校区", "校区", "网络报障", "招生章程", "招生简章",
    "普通高考", "研究生", "本科", "申请表", "培养方案", "专业目录", "学籍异动",
    "学生证", "招聘会", "双选会", "宣讲会", "通知公告", "校医院", "报修电话",
    "下载", "学校", "申请", "怎么", "如何", "查询", "办理", "什么", "哪个", "哪些",
}, key=len, reverse=True))
_DOMAIN_COMPOUND_PARTS = {
    "招生章程": ("招生", "章程"),
    "招生简章": ("招生", "简章"),
    "普通高考": ("普通", "高考"),
    "网络报障": ("网络", "报障"),
    "学籍异动": ("学籍", "异动"),
    "白云校区": ("校区",),
    "海珠校区": ("校区",),
}
LEXICAL_STOPWORDS = {
    "下载", "学校", "申请", "怎么", "如何", "查询", "办理", "什么", "哪个", "哪些",
    "年", "有", "几个", "多少", "主要", "讲", "介绍", "哪里", "在哪", "吗", "呢",
    "仲恺农业工程学院",
}
QUERY_EXPANSIONS = {
    "本科": ("普通高考",),
    "网络报障": ("网络故障",),
    "招聘会": ("双选会", "宣讲会"),
}


def _fallback_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for segment in re.findall(r"[A-Za-z]+(?:[-_][A-Za-z0-9]+)*|\d+(?:\.\d+)?|[\u4e00-\u9fff]+", value):
        if not re.fullmatch(r"[\u4e00-\u9fff]+", segment):
            tokens.append(segment)
            continue
        cursor = 0
        while cursor < len(segment):
            match = next((term for term in _DOMAIN_TERMS if segment.startswith(term, cursor)), None)
            if match:
                tokens.append(match)
                cursor += len(match)
            else:
                tokens.append(segment[cursor])
                cursor += 1
    return tokens


def _expand_domain_tokens(tokens: list[str]) -> list[str]:
    expanded = list(tokens)
    for token in tokens:
        expanded.extend(_DOMAIN_COMPOUND_PARTS.get(token, ()))
    return expanded


def tokenize(text: str) -> list[str]:
    """中文优先使用 jieba；不可用时按汉字/英文/数字 token 化。"""
    value = str(text or "").lower()
    if jieba is not None:
        tokens = [token.strip() for token in jieba.lcut(value) if token.strip() and not token.isspace()]
        return _expand_domain_tokens(tokens)
    return _expand_domain_tokens(_fallback_tokens(value))


@dataclass(frozen=True)
class LexicalDocument:
    doc_id: str
    text: str
    metadata: dict[str, Any]


class LexicalIndex:
    """内存 BM25 索引，支持按 collection 独立重建。"""

    FIELD_WEIGHTS = {
        "title": 4.0,
        "chapter": 3.0,
        "structured": 2.0,
        "body": 1.0,
    }

    def __init__(self, documents: Iterable[LexicalDocument] | None = None) -> None:
        self.documents: dict[str, LexicalDocument] = {}
        self._field_tokens: dict[str, dict[str, list[str]]] = {}
        self._field_lengths: dict[str, dict[str, int]] = defaultdict(dict)
        self._field_df: dict[str, Counter[str]] = defaultdict(Counter)
        self._field_avgdl: dict[str, float] = {}
        if documents:
            self.rebuild(documents)

    def rebuild(self, documents: Iterable[LexicalDocument]) -> None:
        self.documents = {document.doc_id: document for document in documents}
        self._field_tokens = {}
        self._field_lengths = defaultdict(dict)
        self._field_df = defaultdict(Counter)
        self._field_avgdl = {}
        for document in self.documents.values():
            fields = self._document_fields(document)
            self._field_tokens[document.doc_id] = {}
            for field, value in fields.items():
                tokens = tokenize(value)
                self._field_tokens[document.doc_id][field] = tokens
                self._field_lengths[field][document.doc_id] = len(tokens)
                if tokens:
                    self._field_df[field].update(set(tokens))
        for field, lengths in self._field_lengths.items():
            self._field_avgdl[field] = sum(lengths.values()) / len(lengths) if lengths else 0.0

    def upsert(self, documents: Iterable[LexicalDocument]) -> None:
        merged = {**self.documents, **{document.doc_id: document for document in documents}}
        self.rebuild(merged.values())

    def delete(self, doc_ids: Iterable[str]) -> None:
        removed = set(doc_ids)
        self.rebuild(document for key, document in self.documents.items() if key not in removed)

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        candidate_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        query_tokens = [token for token in tokenize(query) if token not in LEXICAL_STOPWORDS]
        expanded = [expanded_token for token in query_tokens for expanded_token in QUERY_EXPANSIONS.get(token, ())]
        query_tokens.extend(token for token in tokenize(" ".join(expanded)) if token not in LEXICAL_STOPWORDS)
        if not query_tokens or not self.documents:
            return []
        candidates = set(self.documents) if candidate_ids is None else candidate_ids
        scored: list[tuple[float, str]] = []
        for doc_id in candidates:
            if doc_id not in self.documents:
                continue
            score = self._score_document(doc_id, query_tokens)
            if score > 0:
                scored.append((score, doc_id))
        scored.sort(key=lambda row: (-row[0], row[1]))
        results: list[dict[str, Any]] = []
        for rank, (score, doc_id) in enumerate(scored[: max(0, top_k)], 1):
            document = self.documents[doc_id]
            results.append({
                "snippet": document.text,
                "title": document.metadata.get("title", ""),
                "department": document.metadata.get("department"),
                "url": document.metadata.get("source_url", ""),
                "publish_date": document.metadata.get("publish_date", ""),
                "score": round(score, 6),
                "bm25_score": round(score, 6),
                "lexical_rank": rank,
                "retrieval_source": "lexical",
                "metadata": dict(document.metadata),
                "chunk_id": doc_id,
            })
        return results

    def _score_document(self, doc_id: str, query_tokens: list[str]) -> float:
        total = 0.0
        for field, weight in self.FIELD_WEIGHTS.items():
            tokens = self._field_tokens.get(doc_id, {}).get(field, [])
            if not tokens:
                continue
            length = len(tokens)
            avgdl = self._field_avgdl.get(field, 0.0) or 1.0
            for token in query_tokens:
                frequency = tokens.count(token)
                if not frequency:
                    continue
                document_frequency = self._field_df[field].get(token, 0)
                document_count = len(self._field_lengths[field]) or 1
                idf = math.log(1 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5))
                normalizer = frequency + 1.5 * (0.25 + 0.75 * length / avgdl)
                total += weight * idf * (frequency * 2.5) / normalizer
        return total

    @classmethod
    def _document_fields(cls, document: LexicalDocument) -> dict[str, str]:
        metadata = document.metadata
        structured = " ".join(
            str(metadata.get(key) or "")
            for key in ("department", "category", "subcategory", "audience", "document_type", "tags", "major_name", "campus", "year", "service_name")
        )
        chapter = " ".join(
            str(metadata.get(key) or "")
            for key in ("chapter", "section", "heading")
        )
        return {
            "title": str(metadata.get("title") or ""),
            "chapter": chapter,
            "structured": structured,
            "body": document.text,
        }
