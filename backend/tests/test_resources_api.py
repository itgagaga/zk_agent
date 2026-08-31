import asyncio

from fastapi import HTTPException

from backend.api import resources
from backend.tools.job_tool import JobDataError


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
