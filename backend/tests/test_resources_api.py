import asyncio
import json

from fastapi import HTTPException

from backend.api import resources
from backend.tools.job_tool import JobDataError
from backend.utils.academic_pipeline import SearchSessionError


class FakeDownloadTool:
    async def run(self, question, **kwargs):
        assert question == "申请表"
        assert kwargs == {
            "category": "教学与教务",
            "audience": "本科生",
            "top_k": 1,
        }
        return {
            "items": [
                {
                    "title": "学生证申请表.docx",
                    "category": "教学与教务",
                    "audience": "本科生",
                    "file_type": "docx",
                    "source_page_url": "https://example.edu/detail.htm",
                    "file_url": "https://example.edu/form.docx",
                    "publish_date": "2026-08-18",
                    "department": "教务部",
                }
            ],
            "total": 7,
            "facets": {
                "categories": ["教学与教务", "财务与报销"],
                "audiences": ["本科生", "全校师生"],
            },
        }


def test_downloads_api_preserves_tool_metadata_total_and_facets(monkeypatch):
    monkeypatch.setattr(resources, "_download_tool", FakeDownloadTool())

    response = asyncio.run(
        resources.list_downloads(
            keyword="申请表",
            category="教学与教务",
            audience="本科生",
            top_k=1,
        )
    ).model_dump()

    assert response["total"] == 7
    assert response["items"][0]["category"] == "教学与教务"
    assert response["items"][0]["audience"] == "本科生"
    assert response["facets"]["categories"] == ["教学与教务", "财务与报销"]


class FakeJobTool:
    async def run(self, question, **kwargs):
        assert question == "Python"
        assert kwargs == {"kind": "posting", "company": "甲公司", "top_k": 1}
        return {
            "total": 2,
            "items": [
                {
                    "id": "1",
                    "kind": "posting",
                    "title": "Python 开发工程师",
                    "company": "甲公司",
                    "published": "2026-08-18",
                    "time": "",
                    "salary": "5K-8K",
                    "education": "本科",
                    "industry": "软件",
                    "location": "广州",
                    "url": "https://job.example/detail?id=1",
                }
            ],
        }


def test_jobs_api_returns_normalized_items(monkeypatch):
    monkeypatch.setattr(resources, "_job_tool", FakeJobTool())
    response = asyncio.run(
        resources.list_jobs(
            kind="posting", keyword="Python", company="甲公司", top_k=1
        )
    ).model_dump()

    assert response["total"] == 2
    assert response["items"][0]["title"] == "Python 开发工程师"
    assert response["items"][0]["url"].endswith("id=1")


def test_jobs_api_maps_data_errors_to_503(monkeypatch):
    class BrokenJobTool:
        async def run(self, question, **kwargs):
            raise JobDataError("损坏的就业数据")

    monkeypatch.setattr(resources, "_job_tool", BrokenJobTool())
    try:
        asyncio.run(
            resources.list_jobs(kind="fair", keyword=None, company=None, top_k=50)
        )
    except HTTPException as error:
        assert error.status_code == 503
        assert error.detail == "就业数据暂不可用"
    else:
        raise AssertionError("expected HTTPException")


def test_jobs_route_rejects_unknown_kind():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(resources.router)
    response = TestClient(app).get("/jobs?kind=unknown")

    assert response.status_code == 422


def test_academic_analysis_normalizes_structured_llm_content(monkeypatch):
    class FakeResponse:
        content = [{"type": "text", "text": "该领域可分为三个研究方向。"}]

    class FakeLLM:
        async def ainvoke(self, prompt):
            return FakeResponse()

    monkeypatch.setattr(resources._answer_generator, "llm", FakeLLM())
    response = asyncio.run(
        resources.analyze_academic(
            resources.AcademicAnalyzeRequest(
                keyword="深度学习",
                papers=[{"title": "A paper", "snippet": "摘要"}],
            )
        )
    )

    assert response["analysis"] == "该领域可分为三个研究方向。"


def test_academic_api_preserves_actual_queries_and_source_failures(monkeypatch):
    class FakeAcademicTool:
        async def run(self, question, **kwargs):
            assert question == "深度学习"
            assert kwargs == {"top_k": 8}
            return {
                "items": [{"title": "Deep learning", "source": "Crossref", "link_verified": True, "link_checked_at": "2026-10-19T00:00:00+00:00"}],
                "llm_query_optimization": {
                    "original": question,
                    "zh_keywords": "深度学习",
                    "en_keywords": "deep learning",
                    "crossref_queries": ["deep learning", "深度学习"],
                    "arxiv_query": "deep learning",
                },
                "source_status": {"Crossref": {"status": "success"}, "arXiv": {"status": "error"}},
                "partial_failure": True,
                "language_summary": {"preferred": "zh", "zh": 0, "en": 1},
                "link_check_summary": {"checked": 2, "rejected": 1, "returned": 1},
            }

    monkeypatch.setattr(resources, "_academic_search_tool", FakeAcademicTool())
    response = asyncio.run(resources.search_academic(keyword="深度学习", top_k=8)).model_dump()
    assert response["total"] == 1
    assert response["llm_query_optimization"]["crossref_queries"] == ["deep learning", "深度学习"]
    assert response["source_status"]["arXiv"]["status"] == "error"
    assert response["partial_failure"] is True
    assert response["language_summary"] == {"preferred": "zh", "zh": 0, "en": 1}
    assert response["items"][0]["link_verified"] is True
    assert response["items"][0]["link_checked_at"] == "2026-10-19T00:00:00+00:00"
    assert response["link_check_summary"]["rejected"] == 1


def test_academic_stream_yields_incrementally_and_closes_on_disconnect(monkeypatch):
    closed = []

    class FakeTool:
        async def stream(self, question, **kwargs):
            assert question == "深度学习"
            assert kwargs == {"top_k": 8, "cursor": None}
            try:
                yield {"type": "progress", "stage": "planning"}
                yield {"type": "results", "result": {
                    "items": [{"title": "中文论文", "link_verified": True, "venue": "internal field"}],
                    "search_status": "running", "search_id": "search-id",
                }}
                await asyncio.Event().wait()
            finally:
                closed.append(True)

    monkeypatch.setattr(resources, "_academic_search_tool", FakeTool())

    async def scenario():
        response = await resources.stream_academic(keyword="深度学习", top_k=8, cursor=None)
        assert response.media_type == "text/event-stream"
        assert response.headers["x-accel-buffering"] == "no"
        body = response.body_iterator
        assert '"progress"' in await anext(body)
        event = json.loads((await anext(body)).removeprefix("data: "))
        assert event["result"]["items"][0]["title"] == "中文论文"
        assert event["result"]["items"][0]["link_verified"]
        assert "venue" not in event["result"]["items"][0]
        await body.aclose()

    asyncio.run(scenario())
    assert closed == [True]


def test_academic_stream_reports_expired_cursor_as_structured_error(monkeypatch):
    class FakeTool:
        async def stream(self, question, **kwargs):
            raise SearchSessionError("搜索记录已过期，请重新搜索。")
            yield

    monkeypatch.setattr(resources, "_academic_search_tool", FakeTool())

    async def scenario():
        response = await resources.stream_academic(keyword="topic", top_k=8, cursor="expired")
        return [chunk async for chunk in response.body_iterator]

    events = asyncio.run(scenario())
    assert json.loads(events[0].removeprefix("data: "))["code"] == "session_expired"
