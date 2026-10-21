import asyncio
import socket

import httpx
import pytest

from backend.utils import academic_links as module
from backend.utils.academic_links import AcademicLinkChecker


def papers(*paths):
    return [{"title": f"Paper {i}", "url": f"https://papers.example/{path}"} for i, path in enumerate(paths)]


@pytest.fixture
def checker(monkeypatch):
    instance = AcademicLinkChecker()

    async def public(url):
        return url.startswith("https://")

    monkeypatch.setattr(instance, "_public_url", public)
    return instance


def mock_http(monkeypatch, handler):
    client = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))


def test_failed_links_are_filtered_and_later_candidates_fill_slots(checker, monkeypatch):
    requests = []

    def handle(request):
        requests.append(request.url.path)
        code = 404 if request.url.path == "/dead" else 403 if request.url.path == "/blocked" else 200
        return httpx.Response(code, content=b"Article content")

    mock_http(monkeypatch, handle)
    checked, summary = asyncio.run(checker.filter(papers("dead", "blocked", "valid1", "valid2"), 2))
    assert [p["url"] for p in checked] == ["https://papers.example/valid1", "https://papers.example/valid2"]
    assert all(p["link_verified"] and p["link_checked_at"] for p in checked)
    assert summary["checked"] == 4
    assert summary["rejected"] == 2
    assert summary["returned"] == 2


def test_doi_redirect_is_followed_to_readable_landing_page(checker, monkeypatch):
    def handle(request):
        if request.url.host == "doi.org":
            return httpx.Response(302, headers={"Location": "https://papers.example/article"})
        return httpx.Response(200, text="Actual article")

    mock_http(monkeypatch, handle)
    checked, _ = asyncio.run(checker.filter([{"title": "Article", "doi": "10.1234/test"}], 1))
    assert checked[0]["url"] == "https://papers.example/article"


def test_doi_redirect_to_dead_publisher_is_not_accepted(checker, monkeypatch):
    def handle(request):
        if request.url.host == "doi.org":
            return httpx.Response(302, headers={"Location": "https://papers.example/article"})
        raise httpx.ConnectError("TLS connection closed")

    mock_http(monkeypatch, handle)
    checked, summary = asyncio.run(checker.filter([{"title": "Article", "url": "https://doi.org/10.1234/test"}], 1))
    assert checked == []
    assert summary["rejected"] == 1


@pytest.mark.parametrize("status", [204, 404, 410, 403, 429, 500, 503])
def test_empty_or_error_responses_are_rejected(checker, monkeypatch, status):
    mock_http(monkeypatch, lambda request: httpx.Response(status))
    checked, summary = asyncio.run(checker.filter(papers("article"), 1))
    assert checked == []
    assert summary["rejected"] == 1


def test_success_with_empty_body_is_rejected(checker, monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=b""))
    assert asyncio.run(checker.filter(papers("empty"), 1))[0] == []


def test_checks_use_get_and_do_not_depend_on_head_support(checker, monkeypatch):
    methods = []

    def handle(request):
        methods.append(request.method)
        return httpx.Response(405) if request.method == "HEAD" else httpx.Response(200, text="Article")

    mock_http(monkeypatch, handle)
    assert len(asyncio.run(checker.filter(papers("article"), 1))[0]) == 1
    assert methods == ["GET"]


def test_reads_only_first_content_chunk_and_closes_stream(checker, monkeypatch):
    class Body(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b"%PDF-1.7"
            raise AssertionError("must not download entire PDF")

        async def aclose(self):
            self.closed = True

    body = Body()
    mock_http(monkeypatch, lambda request: httpx.Response(200, stream=body))
    assert len(asyncio.run(checker.filter(papers("paper.pdf"), 1))[0]) == 1
    assert body.closed


def test_body_read_error_is_rejected(checker, monkeypatch):
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise httpx.ReadError("connection closed before body")
            yield b""

    mock_http(monkeypatch, lambda request: httpx.Response(200, stream=Body()))
    assert asyncio.run(checker.filter(papers("article"), 1))[0] == []


@pytest.mark.parametrize("location", [None, "/loop"])
def test_missing_location_and_redirect_loops_are_rejected(checker, monkeypatch, location):
    calls = []

    def handle(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": location} if location else {})

    mock_http(monkeypatch, handle)
    assert asyncio.run(checker.filter(papers("loop"), 1))[0] == []
    assert len(calls) == 1


def test_relative_redirect_is_resolved(checker, monkeypatch):
    def handle(request):
        if request.url.path == "/old":
            return httpx.Response(301, headers={"Location": "/new"})
        return httpx.Response(200, text="Article")

    mock_http(monkeypatch, handle)
    assert asyncio.run(checker.filter(papers("old"), 1))[0][0]["url"].endswith("/new")


def test_duplicate_urls_are_checked_once(checker, monkeypatch):
    calls = []

    def handle(request):
        calls.append(str(request.url))
        return httpx.Response(200, text="Article")

    mock_http(monkeypatch, handle)
    checked, summary = asyncio.run(checker.filter(papers("same", "same"), 2))
    assert len(checked) == 2
    assert len(calls) == 1
    assert summary["checked"] == 2


def test_parallel_completion_preserves_candidate_order(checker, monkeypatch):
    async def scenario():
        second_started = asyncio.Event()

        async def handle(request):
            if request.url.path == "/first":
                await second_started.wait()
            else:
                second_started.set()
            return httpx.Response(200, text="Article")

        mock_http(monkeypatch, handle)
        return await checker.filter(papers("first", "second"), 2)

    checked, _ = asyncio.run(scenario())
    assert [p["url"].rsplit("/", 1)[-1] for p in checked] == ["first", "second"]


def test_stops_after_enough_valid_candidates_and_bounds_concurrency(checker, monkeypatch):
    checker.concurrency = 3
    active = 0
    peak = 0
    calls = []

    async def handle(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        calls.append(request.url.path)
        await asyncio.sleep(0)
        active -= 1
        return httpx.Response(200, text="Article")

    mock_http(monkeypatch, handle)
    checked, summary = asyncio.run(checker.filter(papers(*(str(i) for i in range(12))), 5))
    assert len(checked) == 5
    assert len(calls) == 6
    assert peak == 3
    assert summary["unchecked"] == 6


def test_url_timeout_filters_unresponsive_page(checker, monkeypatch):
    checker.url_timeout = 0.02

    async def handle(request):
        await asyncio.Event().wait()

    mock_http(monkeypatch, handle)
    checked, summary = asyncio.run(checker.filter(papers("slow"), 1))
    assert checked == []
    assert summary["unconfirmed"] == 1
    assert summary["rejected"] == 0


def test_overall_deadline_keeps_completed_checks_and_cancels_rest(checker, monkeypatch):
    checker.budget = 0.03
    cancelled = []

    async def handle(request):
        if request.url.path == "/fast":
            return httpx.Response(200, text="Article")
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    mock_http(monkeypatch, handle)
    checked, summary = asyncio.run(checker.filter(papers("fast", "slow"), 2))
    assert len(checked) == 1 and checked[0]["url"].endswith("/fast")
    assert summary["timed_out"] is True
    assert summary["checked"] == 1
    assert summary["unchecked"] == 1
    assert cancelled == [True]


@pytest.mark.parametrize("url", [
    "", "file:///etc/passwd", "ftp://papers.example/article", "https://localhost/article",
    "http://127.0.0.1", "http://[::1]", "https://10.0.0.1/article", "http://169.254.169.254",
    "https://user:password@papers.example/article", "https://8.8.8.8:9000/article",
])
def test_unsafe_urls_are_rejected_without_http_requests(monkeypatch, url):
    def handle(request):
        raise AssertionError("unsafe URL must not be requested")

    mock_http(monkeypatch, handle)
    checked, _ = asyncio.run(AcademicLinkChecker().filter([{"title": "Article", "url": url}], 1))
    assert checked == []


def test_redirect_to_private_network_is_not_followed(monkeypatch):
    calls = []

    def handle(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})

    mock_http(monkeypatch, handle)
    checked, _ = asyncio.run(AcademicLinkChecker().filter([{"title": "Article", "url": "https://8.8.8.8/article"}], 1))
    assert checked == []
    assert calls == ["https://8.8.8.8/article"]


def test_public_hostname_resolving_to_private_ip_is_rejected(monkeypatch):
    async def scenario():
        async def resolve(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        return await AcademicLinkChecker()._public_url("https://papers.example/article")

    assert asyncio.run(scenario()) is False


def test_rolling_queue_uses_freed_slot_before_slow_request_finishes(checker, monkeypatch):
    checker.concurrency = 2

    async def scenario():
        third_started = asyncio.Event()

        async def handle(request):
            if request.url.path == "/slow":
                await third_started.wait()
            elif request.url.path == "/dead":
                return httpx.Response(404)
            else:
                third_started.set()
            return httpx.Response(200, text="Article")

        mock_http(monkeypatch, handle)
        return await checker.filter(papers("slow", "dead", "third"), 2)

    checked, _ = asyncio.run(asyncio.wait_for(scenario(), timeout=2))
    assert [p["url"].rsplit("/", 1)[-1] for p in checked] == ["slow", "third"]


def test_repeated_connection_failures_skip_remaining_same_host(checker, monkeypatch):
    checker.concurrency = 1
    calls = []

    def handle(request):
        calls.append(str(request.url))
        raise httpx.ConnectError("TLS closed")

    mock_http(monkeypatch, handle)
    checked, summary = asyncio.run(checker.filter(papers("a", "b", "c", "d"), 2))
    assert checked == []
    assert len(calls) == 2
    assert summary["rejected"] == 4
