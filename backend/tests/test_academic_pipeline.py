import asyncio
import json
from contextlib import nullcontext

import pytest

from backend.config import settings
from backend.tools.academic_search_tool import AcademicSearchTool
from backend.utils.academic_links import AcademicLinkChecker
from backend.utils.academic_pipeline import SearchSessionError


def paper(title, source="Crossref"):
    return {"title": title, "source": source, "url": f"https://papers.example/{title}", "cited": 0}


@pytest.fixture
def tool(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    tool = AcademicSearchTool()

    async def empty(query, limit):
        return []

    monkeypatch.setattr(tool, "_search_crossref", empty)
    monkeypatch.setattr(tool, "_search_arxiv", empty)
    return tool


def fake_checks(tool, monkeypatch, probe):
    def make_checker():
        checker = AcademicLinkChecker()
        monkeypatch.setattr(checker, "client", lambda: nullcontext(None))
        monkeypatch.setattr(checker, "_probe", probe)
        return checker
    monkeypatch.setattr(tool, "_make_link_checker", make_checker)


def test_common_terms_skip_model_and_have_bilingual_search_plan(tool):
    class ForbiddenLLM:
        async def ainvoke(self, prompt):
            raise AssertionError("common term must not call LLM")

    tool.llm = ForbiddenLLM()
    for question, expected in [("软件工程", "software engineering"), ("深度学习", "deep learning"), ("computer vision", "computer vision")]:
        result = asyncio.run(tool.run(question))
        assert result["query_used"]["en"] == expected


def test_complex_query_reuses_bounded_keyword_cache(tool):
    calls = []

    class LLM:
        async def ainvoke(self, prompt):
            calls.append(prompt)
            return json.dumps({"zh_keywords": "蛋白质 相互作用", "en_keywords": "protein interactions"})

    tool.llm = LLM()
    question = "寻找蛋白质相互作用的前沿研究"
    assert asyncio.run(tool.optimize_query(question)) == ("蛋白质 相互作用", "protein interactions")
    assert asyncio.run(tool.optimize_query(question)) == ("蛋白质 相互作用", "protein interactions")
    assert len(calls) == 1


def test_source_results_start_verification_before_other_source_finishes(tool, monkeypatch):
    async def scenario():
        verified = asyncio.Event()

        async def crossref(query, limit):
            return [paper("topic first")]

        async def arxiv(query, limit):
            await verified.wait()
            return [paper("topic second", "arXiv")]

        async def probe(client, url):
            verified.set()
            return url

        monkeypatch.setattr(tool, "_search_crossref", crossref)
        monkeypatch.setattr(tool, "_search_arxiv", arxiv)
        fake_checks(tool, monkeypatch, probe)
        return await asyncio.wait_for(tool.run("topic", top_k=2), timeout=2)

    result = asyncio.run(scenario())
    assert result["total"] == 2
    assert result["timing"]["first_result_ms"] is not None
    assert result["search_status"] == "complete"


def test_stream_emits_verified_result_before_slow_source_and_closes_cleanly(tool, monkeypatch):
    async def scenario():
        cancelled = asyncio.Event()

        async def crossref(query, limit):
            return [paper("topic first")]

        async def arxiv(query, limit):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def probe(client, url):
            return url

        monkeypatch.setattr(tool, "_search_crossref", crossref)
        monkeypatch.setattr(tool, "_search_arxiv", arxiv)
        fake_checks(tool, monkeypatch, probe)
        events = tool.stream("topic", top_k=2)
        try:
            async for event in events:
                if event.get("result", {}).get("items"):
                    assert all(p["link_verified"] for p in event["result"]["items"])
                    assert event["result"]["source_status"]["arXiv"]["status"] == "pending"
                    break
        finally:
            await events.aclose()
        assert cancelled.is_set()
        assert not next(iter(tool._pipeline.sessions.values())).active

    asyncio.run(asyncio.wait_for(scenario(), timeout=2))


def test_deadline_preserves_results_and_continuation_resumes_candidates(tool, monkeypatch):
    monkeypatch.setattr(settings, "academic_search_timeout_seconds", 0.06)

    async def scenario():
        release = asyncio.Event()
        calls = {"source": 0, "fast": 0, "slow": 0}

        async def crossref(query, limit):
            calls["source"] += 1
            return [paper("topic fast"), paper("topic slow")]

        async def probe(client, url):
            key = "slow" if url.endswith("slow") else "fast"
            calls[key] += 1
            if key == "slow":
                await release.wait()
            return url

        monkeypatch.setattr(tool, "_search_crossref", crossref)
        fake_checks(tool, monkeypatch, probe)
        first = await tool.run("topic", top_k=2)
        assert first["total"] == 1
        assert first["search_status"] == "partial"
        assert first["link_check_summary"]["timed_out"]
        assert first["continuation_cursor"]
        release.set()
        second = await tool.run("topic", top_k=2, cursor=first["continuation_cursor"])
        assert second["total"] == 2
        assert second["search_status"] == "complete"
        assert second["continuation_cursor"] is None
        assert calls == {"source": 1, "fast": 1, "slow": 2}

    asyncio.run(scenario())


def test_continuation_retries_only_unfinished_source(tool, monkeypatch):
    monkeypatch.setattr(settings, "academic_search_timeout_seconds", 0.06)

    async def scenario():
        release = asyncio.Event()
        calls = {"Crossref": 0, "arXiv": 0}

        async def crossref(query, limit):
            calls["Crossref"] += 1
            return [paper("topic first")]

        async def arxiv(query, limit):
            calls["arXiv"] += 1
            await release.wait()
            return [paper("topic second", "arXiv")]

        async def probe(client, url):
            return url

        monkeypatch.setattr(tool, "_search_crossref", crossref)
        monkeypatch.setattr(tool, "_search_arxiv", arxiv)
        fake_checks(tool, monkeypatch, probe)
        first = await tool.run("topic", top_k=2)
        assert first["source_status"]["arXiv"]["status"] == "pending"
        release.set()
        second = await tool.run("topic", top_k=2, cursor=first["continuation_cursor"])
        assert second["total"] == 2
        assert calls == {"Crossref": 1, "arXiv": 2}

    asyncio.run(scenario())


def test_pipeline_keeps_chinese_priority_when_english_source_finishes_first(tool, monkeypatch):
    async def scenario():
        english_checked = asyncio.Event()

        async def crossref(query, limit):
            if "深度学习" in query:
                await english_checked.wait()
                return [paper("深度学习图像识别")]
            return [paper("Deep learning neural networks")]

        async def probe(client, url):
            if "Deep" in url:
                english_checked.set()
            return url

        monkeypatch.setattr(tool, "_search_crossref", crossref)
        fake_checks(tool, monkeypatch, probe)
        return await asyncio.wait_for(tool.run("深度学习", top_k=1), timeout=2)

    result = asyncio.run(scenario())
    assert result["items"][0]["title"] == "深度学习图像识别"


def test_url_timeout_is_unknown_and_retryable_on_continuation(tool, monkeypatch):
    attempts = []

    async def crossref(query, limit):
        return [paper("topic")]

    def make_checker():
        checker = AcademicLinkChecker()
        monkeypatch.setattr(checker, "client", lambda: nullcontext(None))
        async def probe(client, url):
            attempts.append(url)
            if len(attempts) == 1:
                checker._unconfirmed.add(url)
                return None
            return url
        monkeypatch.setattr(checker, "_probe", probe)
        return checker

    monkeypatch.setattr(tool, "_search_crossref", crossref)
    monkeypatch.setattr(tool, "_make_link_checker", make_checker)

    async def scenario():
        first = await tool.run("topic", top_k=1)
        assert first["link_check_summary"]["unconfirmed"] == 1
        assert first["link_check_summary"]["rejected"] == 0
        second = await tool.run("topic", top_k=1, cursor=first["continuation_cursor"])
        assert second["total"] == 1
    asyncio.run(scenario())


def test_invalid_or_expired_continuation_is_reported(tool):
    with pytest.raises(SearchSessionError, match="过期"):
        asyncio.run(tool.run("topic", cursor="missing"))


def test_new_search_rechecks_links_instead_of_reusing_stale_success(tool, monkeypatch):
    calls = []

    async def crossref(query, limit):
        return [paper("topic")]

    async def probe(client, url):
        calls.append(url)
        return url if len(calls) == 1 else None

    monkeypatch.setattr(tool, "_search_crossref", crossref)
    fake_checks(tool, monkeypatch, probe)
    assert asyncio.run(tool.run("topic"))["total"] == 1
    assert asyncio.run(tool.run("topic"))["total"] == 0
    assert len(calls) == 2


def test_keyword_planning_timeout_falls_back_and_cancels_model(tool, monkeypatch):
    monkeypatch.setattr(settings, "academic_query_timeout_seconds", 0.01)
    cancelled = []

    class LLM:
        async def ainvoke(self, prompt):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)

    tool.llm = LLM()
    result = asyncio.run(tool.run("寻找蛋白质相互作用研究"))
    assert result["query_used"]["zh"]
    assert cancelled == [True]


@pytest.mark.parametrize("failure", ["timeout", "503"])
def test_transient_source_error_can_be_retried_on_continuation(tool, monkeypatch, failure):
    import httpx
    calls = []

    async def crossref(query, limit):
        calls.append(query)
        if len(calls) == 1:
            if failure == "503":
                response = httpx.Response(503, request=httpx.Request("GET", "https://api.crossref.org/works"))
                response.raise_for_status()
            raise httpx.ReadTimeout("temporary failure")
        return [paper("topic")]

    async def probe(client, url):
        return url

    monkeypatch.setattr(tool, "_search_crossref", crossref)
    fake_checks(tool, monkeypatch, probe)

    async def scenario():
        first = await tool.run("topic", top_k=1)
        assert first["continuation_cursor"]
        second = await tool.run("topic", top_k=1, cursor=first["continuation_cursor"])
        assert second["total"] == 1
        assert len(calls) == 2

    asyncio.run(scenario())


def test_fast_keywords_do_not_strip_constraints_from_natural_language(tool):
    calls = []

    class LLM:
        async def ainvoke(self, prompt):
            calls.append(prompt)
            return json.dumps({"zh_keywords": "深度学习", "en_keywords": "deep learning"})

    tool.llm = LLM()
    asyncio.run(tool.optimize_query("帮我找深度学习相关的最新论文"))
    assert len(calls) == 1
    assert "最新论文" in calls[0]
