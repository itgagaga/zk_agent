"""Task 9：语义 RAG 黄金集结构和覆盖范围。"""
from __future__ import annotations

from collections import Counter

from analytics.rag_semantic_evaluation import BUSINESS_RETRIEVERS, load_gold_cases


def test_semantic_gold_has_required_shape_and_balanced_categories():
    cases = load_gold_cases()
    assert len(cases) == 200
    assert len({case.id for case in cases}) == len(cases)
    assert Counter(case.category for case in cases) == Counter({
        "direct": 60,
        "paraphrase": 60,
        "followup": 30,
        "multi_intent": 30,
        "negative": 20,
    })
    assert all(case.question for case in cases)
    assert all(case.expected_gate in {"supported", "partial", "unsupported"} for case in cases)


def test_each_business_retriever_has_at_least_twenty_gold_cases():
    cases = load_gold_cases()
    counts = Counter(
        retriever
        for case in cases
        for retriever in case.expected_retrievers
    )

    for retriever in BUSINESS_RETRIEVERS:
        assert counts[retriever] >= 20, (retriever, counts[retriever])


def test_negative_cases_protect_private_document_scope():
    cases = load_gold_cases()
    negatives = [case for case in cases if case.category == "negative"]
    private_scope_cases = [
        case for case in negatives if "user_docs" in case.forbidden_retrievers
    ]

    assert negatives
    assert len(private_scope_cases) >= 4
    assert all(case.expected_gate == "unsupported" for case in negatives)
