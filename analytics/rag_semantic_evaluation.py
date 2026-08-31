"""语义 RAG 黄金集的离线评测入口。

默认只评测 Query Planner，不调用外部 LLM/API；提供 ``--api-base`` 时，
对填写了 ``expected_doc_ids`` 的用例追加在线 Recall@K 评测。
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from analytics.core import calculate_recall_at_k
from analytics.evaluation import micro_f1_from_counts, retrieval_selection_counts
from backend.rag.query_planner import QueryPlanner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLD_PATH = PROJECT_ROOT / "analytics" / "fixtures" / "rag_semantic_gold.json"
BUSINESS_RETRIEVERS = (
    "weather_search",
    "map_route",
    "job_search",
    "news_search",
    "contact_search",
    "service_link_search",
    "download_search",
    "major_search",
    "academic_search",
)
THRESHOLDS = {
    "retriever_selection_micro_f1": 0.90,
    "private_doc_false_positive_rate": 0.02,
    "standalone_entity_preservation": 0.95,
}


@dataclass(frozen=True)
class GoldCase:
    id: str
    question: str
    history: list[dict[str, str]] = field(default_factory=list)
    category: str = "direct"
    expected_retrievers: set[str] = field(default_factory=set)
    forbidden_retrievers: set[str] = field(default_factory=set)
    expected_entities: dict[str, str] = field(default_factory=dict)
    expected_doc_ids: set[str] = field(default_factory=set)
    expected_gate: str | None = None


def load_gold_cases(path: str | Path | None = None) -> list[GoldCase]:
    """加载并做基础字段校验，不依赖外部服务。"""
    fixture = Path(path) if path else DEFAULT_GOLD_PATH
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("semantic gold fixture must be a JSON list")

    cases: list[GoldCase] = []
    seen_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each semantic gold case must be an object")
        required = {"id", "question", "expected_retrievers", "forbidden_retrievers", "expected_entities", "expected_doc_ids", "expected_gate"}
        missing = required - item.keys()
        if missing:
            raise ValueError(f"case {item.get('id', '<unknown>')} missing fields: {sorted(missing)}")
        case_id = str(item["id"])
        if case_id in seen_ids:
            raise ValueError(f"duplicate semantic gold id: {case_id}")
        seen_ids.add(case_id)
        cases.append(
            GoldCase(
                id=case_id,
                question=str(item["question"]),
                history=[
                    {"role": str(entry.get("role", "user")), "content": str(entry.get("content", ""))}
                    for entry in (item.get("history") or [])
                ],
                category=str(item.get("category", "direct")),
                expected_retrievers=set(map(str, item["expected_retrievers"])),
                forbidden_retrievers=set(map(str, item["forbidden_retrievers"])),
                expected_entities={str(k): str(v) for k, v in item["expected_entities"].items()},
                expected_doc_ids=set(map(str, item["expected_doc_ids"])),
                expected_gate=str(item["expected_gate"]) if item["expected_gate"] is not None else None,
            )
        )
    return cases


async def _offline_plans(cases: Iterable[GoldCase]) -> list[Any]:
    planner = QueryPlanner()
    # The golden set is a deterministic regression gate. Never call online LLMs here.
    planner._structured_llm = None
    return [
        planner._rule_plan(
            case.question,
            history=case.history,
            user_id=None,
            context_hint=None,
        )
        for case in cases
    ]


def evaluate_planner(cases: list[GoldCase] | None = None) -> dict[str, Any]:
    """计算离线 Planner 指标和每条用例的可审计结果。"""
    gold = cases or load_gold_cases()
    plans = asyncio.run(_offline_plans(gold))
    expected = [case.expected_retrievers for case in gold]
    predicted = [set(plan.retrievers) for plan in plans]
    counts = retrieval_selection_counts(expected, predicted)

    entity_total = 0
    entity_kept = 0
    subquestion_expected = 0
    subquestion_exact = 0
    private_denominator = 0
    private_false_positives = 0
    case_results: list[dict[str, Any]] = []
    for case, plan, guess in zip(gold, plans, predicted):
        entities = {
            key: value
            for subquestion in plan.subquestions
            for key, value in subquestion.entities.items()
        }
        entity_total += len(case.expected_entities)
        entity_kept += sum(
            entities.get(key) == value
            for key, value in case.expected_entities.items()
        )
        if "user_docs" in case.forbidden_retrievers:
            private_denominator += 1
            private_false_positives += int("user_docs" in guess)
        if case.category == "followup" and case.history:
            # A follow-up must retain the historical context in the standalone query.
            subquestion_expected += 1
            subquestion_exact += int(
                plan.used_history and len(plan.standalone_query) >= len(case.question)
            )
        case_results.append(
            {
                "id": case.id,
                "category": case.category,
                "expected_retrievers": sorted(case.expected_retrievers),
                "predicted_retrievers": sorted(guess),
                "missing_retrievers": sorted(case.expected_retrievers - guess),
                "unexpected_retrievers": sorted(guess - case.expected_retrievers),
                "standalone_query": plan.standalone_query,
                "planner_source": plan.planner_source,
                "used_history": plan.used_history,
            }
        )

    metrics = {
        "retriever_selection_micro_f1": micro_f1_from_counts(counts),
        "private_doc_false_positive_rate": (
            private_false_positives / private_denominator
            if private_denominator
            else 0.0
        ),
        "standalone_entity_preservation": entity_kept / entity_total if entity_total else 1.0,
        "followup_context_preservation": subquestion_exact / subquestion_expected if subquestion_expected else 1.0,
        "selection_counts": counts,
        "case_count": len(gold),
        "category_counts": dict(Counter(case.category for case in gold)),
    }
    metrics["thresholds"] = {
        name: {"value": metrics[name], "minimum": threshold, "passed": metrics[name] >= threshold}
        if name != "private_doc_false_positive_rate"
        else {"value": metrics[name], "maximum": threshold, "passed": metrics[name] <= threshold}
        for name, threshold in THRESHOLDS.items()
    }
    metrics["passed"] = all(item["passed"] for item in metrics["thresholds"].values())
    return {"metrics": metrics, "cases": case_results}


def evaluate_live_retrieval(
    api_base: str,
    cases: list[GoldCase] | None = None,
    *,
    timeout: int = 90,
) -> dict[str, Any]:
    """调用运行中的 API，统计 Gate、引用和可计算的 Recall@K。"""
    import requests

    gold = cases or load_gold_cases()
    recall_cases = [case for case in gold if case.expected_doc_ids]

    ranked: list[list[str]] = []
    expected: list[set[str]] = []
    citations: list[bool] = []
    gate_expected: list[str] = []
    gate_actual: list[str] = []
    for case in gold:
        response = requests.get(
            f"{api_base.rstrip('/')}/api/search/rag",
            params={"q": case.question, "top_k": 10},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        hits = payload.get("hits", [])
        ids = [
            str(hit.get("chunk_id") or (hit.get("metadata") or {}).get("doc_id") or "")
            for hit in hits
        ]
        summary = payload.get("retrieval_summary") or {}
        actual_gate = (summary.get("evidence_assessment") or {}).get("status")
        if case.expected_gate and actual_gate:
            gate_expected.append(case.expected_gate)
            gate_actual.append(str(actual_gate))
        if case.expected_doc_ids:
            ranked.append(ids)
            expected.append(case.expected_doc_ids)
            sources = summary.get("sources") or payload.get("sources") or []
            citations.append(any(
                str(source.get("evidence_id") or source.get("chunk_id") or "")
                in case.expected_doc_ids
                for source in sources
            ))

    gate_correct = sum(expected_gate == actual_gate for expected_gate, actual_gate in zip(gate_expected, gate_actual))
    unsupported_cases = [index for index, value in enumerate(gate_expected) if value == "unsupported"]
    false_supported = sum(gate_actual[index] == "supported" for index in unsupported_cases)
    result: dict[str, Any] = {
        "available": True,
        "case_count": len(gold),
        "gate_case_count": len(gate_expected),
        "gate_accuracy": gate_correct / len(gate_expected) if gate_expected else None,
        "evidence_false_supported_rate": false_supported / len(unsupported_cases) if unsupported_cases else None,
        "citation_support_rate": sum(citations) / len(citations) if citations else None,
    }
    if recall_cases:
        result["recall_case_count"] = len(recall_cases)
        result["recall_at_k"] = calculate_recall_at_k(ranked, expected, [1, 5, 10])
    else:
        result["recall_case_count"] = 0
        result["recall_at_k"] = None
        result["recall_note"] = "黄金集尚未填写稳定 expected_doc_ids"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="评测语义 RAG 黄金集")
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD_PATH)
    parser.add_argument("--api-base", help="可选：运行中后端的 API 地址")
    parser.add_argument("--strict", action="store_true", help="指标未达门槛时返回非零退出码")
    args = parser.parse_args()

    cases = load_gold_cases(args.gold)
    result: dict[str, Any] = {"planner": evaluate_planner(cases)}
    if args.api_base:
        result["retrieval"] = evaluate_live_retrieval(args.api_base, cases)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not args.strict or result["planner"]["metrics"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
