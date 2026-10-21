import asyncio
import json
from urllib.parse import quote

import httpx
import pytest

from backend.tools import academic_search_tool as module
from backend.tools.academic_search_tool import AcademicSearchTool
from backend.utils.academic_links import AcademicLinkChecker


@pytest.fixture
def tool(monkeypatch):
    monkeypatch.setattr(module.settings, "deepseek_api_key", "")
    tool = AcademicSearchTool()
    # 检索/排序测试使用真实调度器，隔离外部原文网络。
    def make_checker():
        checker = AcademicLinkChecker()
        async def probe(client, url):
            return url
        monkeypatch.setattr(checker, "_probe", probe)
        return checker
    monkeypatch.setattr(tool, "_make_link_checker", make_checker)
    return tool


def paper(title, source="Crossref", **extra):
    return {"title": title, "source": source, "snippet": "", "doi": "", "cited": 0,
            "url": f"https://papers.example/{quote(title)}", **extra}


def mock_http(monkeypatch, handler):
    client = httpx.AsyncClient
    monkeypatch.setattr(
        module.httpx, "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_full_crossref_results_do_not_discard_arxiv(tool, monkeypatch):
    async def crossref(query, limit):
        return [paper(f"Deep learning crossref study {i}") for i in range(12)]

    async def arxiv(query, limit):
        assert limit >= 8
        return [paper(f"Deep learning arxiv study {i}", "arXiv") for i in range(12)]

    monkeypatch.setattr(tool, "_search_crossref", crossref)
    monkeypatch.setattr(tool, "_search_arxiv", arxiv)
    result = asyncio.run(tool.run("深度学习", top_k=8))

    assert result["total"] == len(result["items"]) == 8
    assert {p["source"] for p in result["items"]} == {"Crossref", "arXiv"}
    assert result["llm_query_optimization"]["crossref_queries"] == ["deep learning neural networks", "深度学习 神经网络"]
    assert result["source_status"]["arXiv"]["selected_count"] > 0


def test_sources_are_requested_in_parallel(tool, monkeypatch):
    async def scenario():
        started = []
        all_started = asyncio.Event()
        release = asyncio.Event()

        async def search(query, limit):
            started.append(query)
            if len(started) == 3:
                all_started.set()
            await release.wait()
            return []

        monkeypatch.setattr(tool, "_search_crossref", search)
        monkeypatch.setattr(tool, "_search_arxiv", search)
        task = asyncio.create_task(tool.run("深度学习"))
        try:
            await asyncio.wait_for(all_started.wait(), timeout=1)
        finally:
            release.set()
            await task
        assert len(started) == 3

    asyncio.run(scenario())


def test_keyword_optimization_runs_once_and_actual_queries_are_returned(tool, monkeypatch):
    monkeypatch.setattr(tool, "_fast_keywords", lambda question: None)
    calls = []

    class LLM:
        async def ainvoke(self, prompt):
            calls.append(prompt)
            return json.dumps({"zh_keywords": "深度学习", "en_keywords": "deep learning"})

    tool.llm = LLM()
    queries = []

    def handle(request):
        queries.append((request.url.host, dict(request.url.params)))
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json={"message": {"items": []}})
        return httpx.Response(200, text='<feed xmlns="http://www.w3.org/2005/Atom"/>')

    mock_http(monkeypatch, handle)
    result = asyncio.run(tool.run("深度学习"))

    assert len(calls) == 1
    assert {q["query.bibliographic"] for host, q in queries if host == "api.crossref.org"} == {"深度学习 神经网络", "deep learning neural networks"}
    assert all('type:journal-article' in q['filter'] for host, q in queries if host == "api.crossref.org")
    assert next(q for host, q in queries if host == "export.arxiv.org")["search_query"] == 'all:"deep learning"'
    assert result["llm_query_optimization"]["original"] == "深度学习"
    assert result["llm_query_optimization"]["arxiv_query"] == "deep learning"


def test_relevance_precedes_source_order_and_citation_count():
    batches = [{"source": "Crossref", "items": [
        paper("Unrelated learning strategies", cited=100000),
        paper("Deep learning with neural networks"),
    ]}]
    result = AcademicSearchTool._rank_items(batches, "深度学习", "深度学习", "deep learning")
    assert result[0]["title"] == "Deep learning with neural networks"


def test_computing_deep_learning_excludes_pedagogy_but_keeps_technical_education():
    batches = [{"source": "Crossref", "items": [
        paper("尊重幼儿，多维互动，深度学习，共同成长"),
        paper("面向深度学习的小学信息科技教学创新研究"),
        paper("深度学习神经网络在课堂行为识别中的应用"),
    ]}]
    result = AcademicSearchTool._rank_items(batches, "深度学习", "深度学习", "deep learning")
    assert len(result) == 1
    assert "神经网络" in result[0]["title"]


def test_explicit_education_query_preserves_pedagogy():
    batches = [{"source": "Crossref", "items": [paper("小学课堂深度学习教学策略")]}]
    result = AcademicSearchTool._rank_items(batches, "小学课堂深度学习", "小学课堂深度学习", "deep learning education")
    assert len(result) == 1


def test_deduplication_uses_doi_and_full_normalized_title():
    prefix = "A very long title about deep learning and neural network research "
    batches = [
        {"source": "Crossref", "items": [
            paper("Journal version", doi="10.1234/ABC", cited=12),
            paper(prefix + "alpha"), paper(prefix + "beta"),
            paper("Deep Learning: A Survey"),
        ]},
        {"source": "arXiv", "items": [
            paper("Preprint version", "arXiv", doi="https://doi.org/10.1234/abc", snippet="An actual abstract"),
            paper("Deep learning — a survey", "arXiv"),
        ]},
    ]
    result = AcademicSearchTool._rank_items(batches, "learning", "learning", "learning")
    assert len(result) == 4
    merged = next(p for p in result if p["doi"])
    assert merged["snippet"] == "An actual abstract"
    assert merged["cited"] == 12
    assert sum(p["title"].startswith(prefix) for p in result) == 2


def test_failed_arxiv_keeps_crossref_and_reports_failure(tool, monkeypatch):
    async def crossref(query, limit):
        return [paper("Deep learning neural networks")]

    async def arxiv(query, limit):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(tool, "_search_crossref", crossref)
    monkeypatch.setattr(tool, "_search_arxiv", arxiv)
    result = asyncio.run(tool.run("深度学习"))
    assert len(result["items"]) == 1
    assert result["partial_failure"] is True
    assert result["source_status"]["Crossref"]["status"] == "success"
    assert result["source_status"]["arXiv"]["status"] == "error"
    assert "超时" in result["source_status"]["arXiv"]["queries"][0]["message"]


def test_one_failed_crossref_language_is_partial_success(tool, monkeypatch):
    async def crossref(query, limit):
        if query == "deep learning neural networks":
            raise httpx.ConnectError("unavailable")
        return [paper("深度学习与神经网络")]

    async def arxiv(query, limit):
        return []

    monkeypatch.setattr(tool, "_search_crossref", crossref)
    monkeypatch.setattr(tool, "_search_arxiv", arxiv)
    result = asyncio.run(tool.run("深度学习"))
    assert result["source_status"]["Crossref"]["status"] == "partial"
    assert result["partial_failure"] is True
    assert len(result["items"]) == 1


@pytest.mark.parametrize("bad_source", ["Crossref", "arXiv"])
def test_http_errors_are_not_reported_as_empty_success(tool, monkeypatch, bad_source):
    def handle(request):
        source = "Crossref" if request.url.host == "api.crossref.org" else "arXiv"
        if source == bad_source:
            return httpx.Response(429)
        if source == "Crossref":
            return httpx.Response(200, json={"message": {"items": []}})
        return httpx.Response(200, text='<feed xmlns="http://www.w3.org/2005/Atom"/>')

    mock_http(monkeypatch, handle)
    result = asyncio.run(tool.run("deep learning"))
    assert result["source_status"][bad_source]["status"] == "error"
    assert result["partial_failure"] is True
    assert "429" in result["source_status"][bad_source]["queries"][0]["message"]


@pytest.mark.parametrize("arxiv_response", [
    "invalid xml", '<html>Unavailable</html>',
    '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Error</title><id>http://arxiv.org/api/errors#bad_query</id></entry></feed>',
])
def test_bad_arxiv_responses_are_source_errors(tool, monkeypatch, arxiv_response):
    def handle(request):
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json={"message": {"items": []}})
        return httpx.Response(200, text=arxiv_response)

    mock_http(monkeypatch, handle)
    result = asyncio.run(tool.run("deep learning"))
    assert result["source_status"]["arXiv"]["status"] == "error"


def test_actual_abstracts_and_arxiv_dois_are_parsed(tool, monkeypatch):
    def handle(request):
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json={"message": {"items": [{
                "title": ["Deep learning journal"], "DOI": "10.1234/journal",
                "abstract": "<jats:p>Neural networks &amp; learning.</jats:p>",
                "published": {"date-parts": [[2025]]},
                "resource": {"primary": {"URL": "https://publisher.example/article"}},
            }]}})
        return httpx.Response(200, text='''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
          <entry><title>Deep learning preprint</title><id>https://arxiv.org/abs/1234.5678</id>
          <summary>Neural networks for prediction.</summary><published>2026-01-01</published>
          <arxiv:doi>10.1234/preprint</arxiv:doi></entry></feed>''')

    mock_http(monkeypatch, handle)
    result = asyncio.run(tool.run("deep learning"))
    journal = next(p for p in result["items"] if p["source"] == "Crossref")
    preprint = next(p for p in result["items"] if p["source"] == "arXiv")
    assert journal["snippet"] == "Neural networks & learning."
    assert journal["year"] == "2025"
    assert journal["url"] == "https://publisher.example/article"
    assert preprint["doi"] == "10.1234/preprint"


def test_untranslated_chinese_skips_arxiv_explicitly(tool, monkeypatch):
    async def crossref(query, limit):
        return []

    monkeypatch.setattr(tool, "_search_crossref", crossref)
    result = asyncio.run(tool.run("古代文学"))
    assert result["source_status"]["Crossref"]["status"] == "success"
    assert result["source_status"]["arXiv"]["status"] == "skipped"
    assert result["partial_failure"] is False


def test_malformed_llm_keywords_fall_back_to_known_translation(tool):
    class LLM:
        async def ainvoke(self, prompt):
            return '{"zh_keywords": null, "en_keywords": ["deep learning"]}'

    tool.llm = LLM()
    assert asyncio.run(tool._optimize_query("深度学习")) == ("深度学习", "deep learning")


@pytest.mark.parametrize("payload", [{"wrong": []}, {"message": {"items": None}}])
def test_invalid_crossref_schema_reports_failure(tool, monkeypatch, payload):
    def handle(request):
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json=payload)
        return httpx.Response(200, text='<feed xmlns="http://www.w3.org/2005/Atom"/>')

    mock_http(monkeypatch, handle)
    result = asyncio.run(tool.run("deep learning"))
    assert result["source_status"]["Crossref"]["status"] == "error"


def test_concurrent_requests_do_not_share_failure_state(tool, monkeypatch):
    async def search(query, limit):
        await asyncio.sleep(0)
        if query == "unavailable":
            raise httpx.ReadTimeout("timeout")
        return []

    monkeypatch.setattr(tool, "_search_crossref", search)
    monkeypatch.setattr(tool, "_search_arxiv", search)

    async def scenario():
        return await asyncio.gather(tool.run("unavailable"), tool.run("available"))

    failed, succeeded = asyncio.run(scenario())
    assert failed["partial_failure"] is True
    assert succeeded["partial_failure"] is False
    assert all(s["status"] == "success" for s in succeeded["source_status"].values())


def test_arxiv_query_groups_phrases_and_explicitly_combines_terms():
    assert AcademicSearchTool._build_arxiv_query("deep learning computer vision agriculture") == (
        'all:"deep learning" AND all:"computer vision" AND all:"agriculture"'
    )


def test_chinese_query_keeps_chinese_papers_ahead_of_english_expansion(tool, monkeypatch):
    async def crossref(query, limit):
        if "深度学习" in query:
            return [paper("尊重幼儿，深度学习共同成长")] + [
                paper(f"基于深度学习的图像识别研究{i}", snippet="采用卷积神经网络进行图像识别。")
                for i in range(8)
            ]
        return [paper(f"Deep learning neural networks study {i}", cited=10000) for i in range(12)]

    async def arxiv(query, limit):
        return [paper(f"Deep learning neural networks preprint {i}", "arXiv") for i in range(12)]

    monkeypatch.setattr(tool, "_search_crossref", crossref)
    monkeypatch.setattr(tool, "_search_arxiv", arxiv)
    result = asyncio.run(tool.run("深度学习", top_k=8))
    assert result["total"] == 8
    assert all("图像识别" in item["title"] for item in result["items"])
    assert result["language_summary"] == {"preferred": "zh", "zh": 8, "en": 0}


def test_english_query_prefers_english_papers():
    batches = [{"source": "Crossref", "items": [
        paper("深度学习神经网络综述", cited=10000),
        paper("Deep learning neural networks"),
    ]}]
    result = AcademicSearchTool._rank_items(batches, "deep learning", "深度学习", "deep learning")
    assert result[0]["title"] == "Deep learning neural networks"


def test_chinese_question_can_explicitly_request_english_papers():
    batches = [{"source": "Crossref", "items": [
        paper("深度学习神经网络综述", cited=10000),
        paper("Deep learning neural networks"),
    ]}]
    result = AcademicSearchTool._rank_items(batches, "帮我找深度学习的英文论文", "深度学习", "deep learning")
    assert result[0]["title"] == "Deep learning neural networks"


def test_unrelated_chinese_title_does_not_outrank_relevant_english_paper():
    batches = [{"source": "Crossref", "items": [
        paper("农田水利基础设施建设研究", cited=10000),
        paper("Deep learning neural networks"),
    ]}]
    result = AcademicSearchTool._rank_items(batches, "深度学习", "深度学习", "deep learning")
    assert result[0]["title"] == "Deep learning neural networks"


def test_bilingual_metadata_for_same_doi_uses_actual_chinese_title():
    batches = [{"source": "Crossref", "items": [
        paper("Deep learning neural network survey", doi="10.1234/survey"),
        paper("深度学习神经网络综述", doi="10.1234/survey"),
    ]}]
    result = AcademicSearchTool._rank_items(batches, "深度学习", "深度学习", "deep learning")
    assert len(result) == 1
    assert result[0]["title"] == "深度学习神经网络综述"
    assert result[0]["doi"] == "10.1234/survey"


def test_missing_chinese_papers_are_reported_as_english_supplement(tool, monkeypatch):
    original_title = "Deep learning neural networks"

    async def crossref(query, limit):
        return [paper(original_title)]

    async def arxiv(query, limit):
        return []

    monkeypatch.setattr(tool, "_search_crossref", crossref)
    monkeypatch.setattr(tool, "_search_arxiv", arxiv)
    result = asyncio.run(tool.run("深度学习"))
    assert result["items"][0]["title"] == original_title
    assert result["language_summary"] == {"preferred": "zh", "zh": 0, "en": 1}


def test_link_check_precedes_limit_and_updates_result_counts(tool, monkeypatch):
    async def crossref(query, limit):
        return [paper(f"深度学习研究{i}", url=f"https://papers.example/{i}") for i in range(6)]

    async def arxiv(query, limit):
        return []

    def make_checker():
        checker = AcademicLinkChecker()
        async def probe(client, url):
            return url if int(url.rsplit("/", 1)[-1]) >= 3 else None
        monkeypatch.setattr(checker, "_probe", probe)
        return checker

    monkeypatch.setattr(tool, "_search_crossref", crossref)
    monkeypatch.setattr(tool, "_search_arxiv", arxiv)
    monkeypatch.setattr(tool, "_make_link_checker", make_checker)
    result = asyncio.run(tool.run("深度学习", top_k=2))
    assert result["total"] == 2
    assert result["source_status"]["Crossref"]["selected_count"] == 2
    assert result["language_summary"]["zh"] == 2
    assert result["link_check_summary"]["rejected"] == 3
