"""Record reproducible latency metrics for the chat SSE endpoint.

The script intentionally stores only timings, statuses, retriever names and
boolean diagnostics. It never writes the question, answer, bearer token, or
retrieved document snippets.

Examples:
    python analytics/chat_latency_smoke.py --base-url http://127.0.0.1:8000 --runs 1
    python analytics/chat_latency_smoke.py --scope with_personal --token-env CHAT_LATENCY_TOKEN
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


DEFAULT_QUESTION = "我是信计大四学生，你有什么建议"
EMPTY_ANSWER = "模型未返回有效回答，请重试。"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument(
        "--scope",
        choices=("auto", "with_personal", "personal_only"),
        default="auto",
    )
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--token", default=None, help="Bearer token; prefer --token-env")
    parser.add_argument("--token-env", default="CHAT_LATENCY_TOKEN")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be >= 1")
    if args.timeout <= 0:
        parser.error("--timeout must be > 0")
    return args


def _event_data(line: str) -> dict[str, Any] | None:
    if not line.startswith("data: "):
        return None
    try:
        payload = json.loads(line[6:])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _run_once(client: httpx.Client, args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    result: dict[str, Any] = {
        "scope": args.scope,
        "http_status": None,
        "router_ms": None,
        "retrieval_ms": None,
        "first_token_ms": None,
        "done_ms": None,
        "done": False,
        "has_answer": False,
        "empty_answer_fallback": False,
        "retrievers": [],
        "error_type": None,
    }
    try:
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={
                "question": args.question,
                "knowledge_scope": args.scope,
                "user_role": "student",
                "history": [],
            },
            timeout=args.timeout,
        ) as response:
            result["http_status"] = response.status_code
            if response.status_code >= 400:
                result["error_type"] = f"http_{response.status_code}"
                return result
            for line in response.iter_lines():
                event = _event_data(line)
                if event is None:
                    continue
                event_type = event.get("type")
                elapsed_ms = (time.perf_counter() - started) * 1000
                if event_type == "router":
                    result["router_ms"] = round(elapsed_ms, 1)
                    result["retrievers"] = event.get("effective_retrievers") or event.get("intents") or []
                elif event_type == "retrieval":
                    result["retrieval_ms"] = round(elapsed_ms, 1)
                elif event_type == "token":
                    content = event.get("content")
                    if content:
                        result["has_answer"] = True
                        if result["first_token_ms"] is None:
                            result["first_token_ms"] = round(elapsed_ms, 1)
                        if content == EMPTY_ANSWER:
                            result["empty_answer_fallback"] = True
                elif event_type == "done":
                    result["done"] = True
                    result["done_ms"] = round(elapsed_ms, 1)
    except httpx.TimeoutException:
        result["error_type"] = "timeout"
    except httpx.HTTPError as exc:
        result["error_type"] = type(exc).__name__
    return result


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    def percentile(field: str, fraction: float) -> float | None:
        values = sorted(
            float(item[field])
            for item in results
            if isinstance(item.get(field), (int, float))
        )
        if not values:
            return None
        index = min(len(values) - 1, round((len(values) - 1) * fraction))
        return round(values[index], 1)

    return {
        "runs": len(results),
        "completed_runs": sum(item["done"] for item in results),
        "answer_runs": sum(item["has_answer"] for item in results),
        "empty_answer_fallbacks": sum(item["empty_answer_fallback"] for item in results),
        "errors": sum(bool(item["error_type"]) for item in results),
        "first_token_ms": {"p50": percentile("first_token_ms", 0.50), "p95": percentile("first_token_ms", 0.95)},
        "done_ms": {"p50": percentile("done_ms", 0.50), "p95": percentile("done_ms", 0.95)},
        "router_ms": {"p50": percentile("router_ms", 0.50), "p95": percentile("router_ms", 0.95)},
        "retrieval_ms": {"p50": percentile("retrieval_ms", 0.50), "p95": percentile("retrieval_ms", 0.95)},
    }


def main() -> int:
    args = _parse_args()
    token = args.token or os.getenv(args.token_env)
    headers = {"Accept": "text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    results: list[dict[str, Any]] = []
    with httpx.Client(base_url=args.base_url.rstrip("/"), headers=headers) as client:
        for _ in range(args.runs):
            results.append(_run_once(client, args))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url.rstrip("/"),
        "scope": args.scope,
        "question_length": len(args.question),
        "summary": _summary(results),
        "runs": results,
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if payload["summary"]["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
