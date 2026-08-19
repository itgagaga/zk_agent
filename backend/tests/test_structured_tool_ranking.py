import asyncio

from backend.tools.contact_tool import ContactTool
from backend.tools.download_tool import DownloadTool
from backend.tools.service_link_tool import ServiceLinkTool


def test_download_tool_ranks_late_exact_domain_match_before_generic_items(monkeypatch):
    monkeypatch.setattr(
        DownloadTool,
        "_load_all_metadata",
        staticmethod(
            lambda: [
                {
                    "category": "教务",
                    "download_items": [
                        {"name": "考试申请表", "url": "/exam.pdf"},
                        {"name": "奖学金申请表", "url": "/scholarship.pdf"},
                        {"name": "缓考申请表", "url": "/late.pdf"},
                    ],
                }
            ]
        ),
    )

    result = asyncio.run(DownloadTool().run("缓考申请表在哪里下载？", top_k=1))

    assert result["items"][0]["title"] == "缓考申请表"
    assert result["items"][0]["file_url"] == "/late.pdf"


def test_download_tool_deduplicates_before_cutting_and_exposes_match_score(monkeypatch):
    monkeypatch.setattr(
        DownloadTool,
        "_load_all_metadata",
        staticmethod(
            lambda: [
                {
                    "download_items": [
                        {"name": "缓考申请表", "url": "/late.pdf"},
                        {"name": "缓考申请表", "url": "/late.pdf"},
                    ]
                }
            ]
        ),
    )

    result = asyncio.run(DownloadTool().run("缓考申请表", top_k=10))

    assert len(result["items"]) == 1
    assert result["items"][0]["match_score"] > 0


def test_structured_tools_return_default_items_for_empty_queries(monkeypatch):
    metadata = [
        {
            "department": "教务部",
            "download_items": [{"name": "学生证申请表", "url": "/student-card.pdf"}],
            "service_links": {"教务系统": "https://example.edu/jwc"},
            "contacts": [{"department": "教务部", "phone": "020-12345678"}],
        }
    ]
    for tool in (DownloadTool, ServiceLinkTool, ContactTool):
        monkeypatch.setattr(tool, "_load_all_metadata", staticmethod(lambda: metadata))

    assert asyncio.run(DownloadTool().run("", top_k=10))["total"] == 1
    assert asyncio.run(ServiceLinkTool().run("", top_k=10))["total"] == 1
    assert asyncio.run(ContactTool().run("", top_k=10))["total"] == 1
