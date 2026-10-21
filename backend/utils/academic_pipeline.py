"""学术检索与链接验证流水线，支持增量快照、统一预算和短期续查。"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import OrderedDict
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from backend.config import settings


class SearchSessionError(ValueError):
    def __init__(self, message, code="session_expired"):
        super().__init__(message)
        self.code = code


@dataclass
class SearchSession:
    question: str
    top_k: int
    token: str = field(default_factory=lambda: uuid.uuid4().hex)
    plan: dict | None = None
    batches: dict = field(default_factory=dict)
    checks: dict = field(default_factory=dict)
    expires: float = field(default_factory=lambda: time.monotonic() + 120)
    active: bool = False


class AcademicSearchPipeline:
    def __init__(self, tool):
        self.tool = tool
        self.sessions: OrderedDict[str, SearchSession] = OrderedDict()

    @staticmethod
    async def _cancel_tasks(*groups):
        tasks = set().union(*(set(group) for group in groups))
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _session(self, question, top_k, cursor):
        now = time.monotonic()
        for token, session in list(self.sessions.items()):
            if not session.active and session.expires <= now:
                self.sessions.pop(token)
        if cursor:
            session = self.sessions.get(cursor)
            if session is None or session.question != question or session.top_k != top_k:
                raise SearchSessionError("搜索记录已过期，请重新搜索。")
            if session.active:
                raise SearchSessionError("这次搜索仍在进行，请等待完成。", "search_running")
            # 续查保留已验证结果；超时是未知状态，允许重试。
            session.checks = {url: o for url, o in session.checks.items() if o["status"] != "unconfirmed"}
            session.batches = {i: b for i, b in session.batches.items() if not b.get("retryable")}
        else:
            while len(self.sessions) >= 32:
                oldest = next((key for key, value in self.sessions.items() if not value.active), None)
                if oldest is None:
                    raise SearchSessionError("搜索繁忙，请稍后重试。", "search_busy")
                self.sessions.pop(oldest)
            session = SearchSession(question, top_k)
            self.sessions[session.token] = session
        self.sessions.move_to_end(session.token)
        return session

    def _ranked(self, session):
        plan = session.plan
        return self.tool._rank_items(
            [session.batches[i] for i in sorted(session.batches)], session.question, plan["zh"], plan["en"],
        )

    def _snapshot(self, session, checker, started, first_result, *, final=False, timed_out=False):
        plan = session.plan
        ranked = self._ranked(session)
        items = [checker.verified(p, session.checks[checker.url_for(p)]) for p in ranked
                 if session.checks.get(checker.url_for(p), {}).get("status") == "available"][:session.top_k]
        summary = checker.summary(ranked, session.checks, items, timed_out)
        sources = {}
        for source in ("Crossref", "arXiv"):
            batches = [session.batches.get(i, {"query": query, "status": "pending", "items": []})
                       for i, (name, query) in enumerate(plan["requests"]) if name == source]
            statuses = [b["status"] for b in batches]
            status = ("skipped" if not batches else "pending" if "pending" in statuses else
                      "success" if all(s == "success" for s in statuses) else
                      "partial" if "success" in statuses else "error")
            sources[source] = {
                "status": status,
                "queries": [{k: v for k, v in b.items() if k not in {"source", "items"}} for b in batches],
                "returned_count": sum(len(b["items"]) for b in batches),
                "selected_count": sum(p["source"] == source for p in items),
            }
        pending_sources = len(session.batches) < len(plan["requests"])
        incomplete = timed_out or pending_sources or summary["unconfirmed"] > 0 or any(b.get("retryable") for b in session.batches.values())
        can_continue = final and (incomplete or (len(items) < session.top_k and summary["unchecked"] > 0))
        return {
            "tool": self.tool.name, "items": items, "total": len(items),
            "query_used": {"zh": plan["zh"], "en": plan["en"]},
            "llm_query_optimization": {"original": session.question, "zh_keywords": plan["zh"],
                                       "en_keywords": plan["en"], "crossref_queries": plan["crossref_queries"], "arxiv_query": plan["en"]},
            "source_status": sources, "partial_failure": any(b["status"] == "error" for b in session.batches.values()),
            "language_summary": {"preferred": self.tool._preferred_language(session.question),
                                 "zh": sum(self.tool._title_language(p["title"]) == "zh" for p in items),
                                 "en": sum(self.tool._title_language(p["title"]) == "en" for p in items)},
            "link_check_summary": summary,
            "search_status": "running" if not final else "partial" if incomplete else "complete",
            "search_id": session.token,
            "continuation_cursor": session.token if can_continue else None,
            "timing": {"elapsed_ms": round((time.monotonic() - started) * 1000), "first_result_ms": first_result},
        }

    async def stream(self, question: str, **kwargs: Any):
        started = time.monotonic()
        deadline = started + settings.academic_search_timeout_seconds
        top_k = max(1, min(int(kwargs.get("top_k", 5)), 20))
        session = self._session(question, top_k, kwargs.get("cursor"))
        session.active = True
        pending_sources, pending_links = {}, {}
        checker = self.tool._make_link_checker()
        first_result = None
        timed_out = False
        enough_since = None
        try:
            yield {"type": "progress", "stage": "planning" if session.plan is None else "resuming"}
            if session.plan is None:
                try:
                    session.plan = await asyncio.wait_for(
                        self.tool.prepare_query(question, top_k, **{k: v for k, v in kwargs.items() if k != "top_k"}),
                        timeout=max(0.001, deadline - time.monotonic()),
                    )
                except TimeoutError:
                    query = self.tool._extract_query(question)
                    session.plan = self.tool.query_plan(question, query, self.tool._to_english_friendly(query), top_k)
            plan = session.plan
            for i, (source, query) in enumerate(plan["requests"]):
                if i not in session.batches:
                    pending_sources[asyncio.create_task(self.tool._fetch_source(source, query, plan["limit"]))] = i
            async with AsyncExitStack() as resources:
                client = await resources.enter_async_context(checker.client())
                resources.push_async_callback(self._cancel_tasks, pending_sources, pending_links)
                while True:
                    snapshot = self._snapshot(session, checker, started, first_result)
                    if snapshot["items"] and first_result is None:
                        first_result = round((time.monotonic() - started) * 1000)
                        snapshot["timing"]["first_result_ms"] = first_result
                    yield {"type": "results", "result": snapshot}
                    ranked = self._ranked(session)
                    full = len(snapshot["items"]) >= top_k
                    preferred_pending = self.tool._preferred_language(question) == "zh" and any(
                        source == "Crossref" and self.tool._title_language(query) == "zh" and i not in session.batches
                        for i, (source, query) in enumerate(plan["requests"])
                    )
                    if full and not preferred_pending:
                        # 不让尚在检查的高排名候选被低排名的快速链接挤掉。
                        available_positions = [i for i, p in enumerate(ranked) if session.checks.get(checker.url_for(p), {}).get("status") == "available"]
                        cutoff = available_positions[top_k - 1]
                        higher_pending = any(checker.url_for(p) not in session.checks for p in ranked[:cutoff])
                        if not higher_pending:
                            enough_since = enough_since or time.monotonic()
                            if not pending_sources or time.monotonic() - enough_since >= 0.5:
                                break
                        else:
                            enough_since = None
                    else:
                        enough_since = None
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        break
                    active_urls = set(pending_links.values())
                    for paper in ranked:
                        if len(pending_links) >= checker.concurrency:
                            break
                        url = checker.url_for(paper)
                        if url not in session.checks and url not in active_urls:
                            pending_links[asyncio.create_task(checker.check(client, url))] = url
                            active_urls.add(url)
                    pending = set(pending_sources) | set(pending_links)
                    if not pending:
                        break
                    wait = remaining
                    if enough_since is not None:
                        wait = min(wait, max(0.001, 0.5 - (time.monotonic() - enough_since)))
                    done, _ = await asyncio.wait(pending, timeout=wait, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        if task in pending_sources:
                            session.batches[pending_sources.pop(task)] = task.result()
                        else:
                            session.checks[pending_links.pop(task)] = task.result()
            session.expires = time.monotonic() + 120
            result = self._snapshot(session, checker, started, first_result, final=True, timed_out=timed_out)
            session.active = False
            yield {"type": "done", "result": result}
        finally:
            await self._cancel_tasks(pending_sources, pending_links)
            session.active = False
