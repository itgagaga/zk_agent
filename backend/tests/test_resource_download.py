from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

import pytest
from backend.tools import base as tools_base
from backend.tools.download_tool import DownloadTool
from crawler.resource_download import (
    build_metadata_record,
    extract_pagination_links,
    extract_resource_links,
    infer_file_type,
    is_document_link,
)


def test_safe_filename_is_unique_for_same_display_name():
    import crawler.resource_download as resource_download

    first = resource_download._safe_filename(
        "下载地址.doc", "https://example.edu/download?id=1", "doc"
    )
    second = resource_download._safe_filename(
        "下载地址.doc", "https://example.edu/download?id=2", "doc"
    )

    assert first != second


@pytest.fixture
def resource_tmp_path():
    root = Path(__file__).resolve().parents[2] / ".tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="resource-test-", dir=root))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_download_tool_reads_nested_resources_and_legacy_field_names(
    monkeypatch, resource_tmp_path
):
    metadata_dir = resource_tmp_path / "metadata" / "jwc"
    metadata_dir.mkdir(parents=True)
    (metadata_dir / "xsxz.json").write_text(
        json.dumps(
            {
                "source_url": "https://example.edu/xsxz.htm",
                "resources": [
                    {
                        "title": "学生证申请表.docx",
                        "file_url": "https://example.edu/form.docx",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(tools_base, "DATA_DIR", resource_tmp_path)

    result = asyncio.run(DownloadTool().run("学生证申请表"))

    assert result["total"] == 1
    assert result["items"][0]["title"] == "学生证申请表.docx"
    assert result["items"][0]["file_url"] == "https://example.edu/form.docx"


def test_download_tool_matches_function_category(monkeypatch, resource_tmp_path):
    metadata_dir = resource_tmp_path / "metadata" / "job"
    metadata_dir.mkdir(parents=True)
    (metadata_dir / "postings.json").write_text(
        json.dumps(
            {
                "title": "公开职位",
                "category": "就业与招聘",
                "download_items": [
                    {
                        "name": "职位详情",
                        "url": "https://example.edu/job/1",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(tools_base, "DATA_DIR", resource_tmp_path)

    result = asyncio.run(DownloadTool().run("就业招聘"))

    assert result["total"] == 1
    assert result["items"][0]["category"] == "就业与招聘"


def test_download_tool_uses_exact_filters_and_resource_metadata(
    monkeypatch, resource_tmp_path
):
    metadata_dir = resource_tmp_path / "metadata" / "mixed"
    metadata_dir.mkdir(parents=True)
    (metadata_dir / "resources.json").write_text(
        json.dumps(
            {
                "title": "混合资料",
                "category": "财务与报销",
                "audience": "全校师生",
                "source_url": "https://example.edu/list.htm",
                "download_items": [
                    {
                        "name": "学生证申请表.docx",
                        "url": "https://example.edu/student-card.docx",
                        "source_page_url": "https://example.edu/student-card.htm",
                        "category": "教学与教务",
                        "audience": "本科生",
                    },
                    {
                        "name": "缓考申请表.docx",
                        "url": "https://example.edu/defer.docx",
                        "category": "教学与教务",
                        "audience": "本科生",
                    },
                    {
                        "name": "报销申请表.xlsx",
                        "url": "https://example.edu/expense.xlsx",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(tools_base, "DATA_DIR", resource_tmp_path)

    result = asyncio.run(
        DownloadTool().run(
            "申请表", category="教学与教务", audience="本科生", top_k=1
        )
    )

    assert result["total"] == 2
    assert len(result["items"]) == 1
    assert result["items"][0]["category"] == "教学与教务"
    assert result["items"][0]["audience"] == "本科生"
    assert result["items"][0]["source_page_url"] == (
        "https://example.edu/student-card.htm"
    )
    assert result["facets"]["categories"] == ["教学与教务", "财务与报销"]


def test_download_tool_category_is_not_used_as_a_keyword(
    monkeypatch, resource_tmp_path
):
    metadata_dir = resource_tmp_path / "metadata"
    metadata_dir.mkdir(parents=True)
    (metadata_dir / "one.json").write_text(
        json.dumps(
            {
                "title": "教学与教务说明",
                "category": "财务与报销",
                "download_items": [
                    {"name": "财务表格.xlsx", "url": "https://example.edu/a.xlsx"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(tools_base, "DATA_DIR", resource_tmp_path)

    result = asyncio.run(DownloadTool().run("", category="教学与教务"))

    assert result["total"] == 0
    assert result["items"] == []


def test_jwc_student_downloads_persists_canonical_download_items(monkeypatch):
    import crawler.crawl_jwc as crawl_jwc

    records = [
        {
            "name": "学生证申请表.docx",
            "url": "https://example.edu/form.docx",
            "source_page_url": "https://example.edu/xsxz.htm",
            "file_type": "docx",
            "status": "downloaded",
            "local_path": "data/raw/jwc/form.docx",
            "error": "",
        }
    ]
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        crawl_jwc,
        "acquire_listing_resources",
        lambda url, source_dir: calls.update(
            {"url": url, "source_dir": source_dir}
        ) or records,
        raising=False,
    )
    monkeypatch.setattr(
        crawl_jwc,
        "write_resource_manifest",
        lambda source_dir, value: calls.update(
            {"manifest_source_dir": source_dir, "manifest_records": value}
        ),
        raising=False,
    )
    monkeypatch.setattr(crawl_jwc, "fetch", lambda url: "<html></html>")
    monkeypatch.setattr(crawl_jwc, "extract_title", lambda soup: "")
    monkeypatch.setattr(crawl_jwc, "save_raw", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_jwc, "save_metadata", lambda *args, **kwargs: None)

    result = crawl_jwc.crawl_student_downloads()

    assert result == records
    assert calls["source_dir"] == "jwc"
    assert calls["manifest_records"] == records


def test_yjs_downloads_persists_canonical_download_items(monkeypatch):
    import crawler.crawl_yjs as crawl_yjs

    records = [{"name": "研究生申请表.pdf", "url": "https://example.edu/form.pdf"}]
    calls: dict[str, object] = {}
    monkeypatch.setattr(
        crawl_yjs,
        "acquire_listing_resources",
        lambda url, source_dir: calls.update(
            {"url": url, "source_dir": source_dir}
        ) or records,
        raising=False,
    )
    monkeypatch.setattr(
        crawl_yjs,
        "write_resource_manifest",
        lambda source_dir, value: calls.update({"manifest_records": value}),
        raising=False,
    )

    result = crawl_yjs.crawl_graduate_downloads()

    assert result == records
    assert calls["source_dir"] == "yjs"
    assert calls["manifest_records"] == records


def test_school_profile_adds_public_page_attachments(monkeypatch):
    import crawler.crawl_zhku_main as crawl_main

    records = [{"name": "学校章程.pdf", "url": "https://example.edu/r.pdf"}]
    calls: dict[str, object] = {}
    monkeypatch.setattr(crawl_main, "fetch", lambda url: "<html></html>")
    monkeypatch.setattr(crawl_main, "parse_html", lambda html: object())
    monkeypatch.setattr(crawl_main, "extract_title", lambda soup: "学校概况")
    monkeypatch.setattr(crawl_main, "extract_main_text", lambda soup: "学校正文")
    monkeypatch.setattr(crawl_main, "extract_publish_date", lambda soup: None)
    monkeypatch.setattr(crawl_main, "extract_attachments", lambda soup, base_url: [])
    monkeypatch.setattr(crawl_main, "acquire_html_resources", lambda *args: records)
    monkeypatch.setattr(
        crawl_main,
        "write_resource_manifest",
        lambda source_dir, value: calls.update({"source_dir": source_dir, "records": value}),
        raising=False,
    )
    monkeypatch.setattr(crawl_main, "save_raw", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_main, "save_cleaned", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_main, "save_metadata", lambda *args, **kwargs: None)

    result = crawl_main.crawl_school_profile()

    assert result["download_items"] == records
    assert calls == {"source_dir": "zhku_main", "records": records}


def test_student_affairs_page_adds_public_page_attachments(monkeypatch):
    import crawler.crawl_extra as crawl_extra

    records = [{"name": "资助申请表.pdf", "url": "https://example.edu/a.pdf"}]
    monkeypatch.setattr(
        crawl_extra,
        "XSC_CONTACTS",
        [{"url": "https://example.edu/info/1.htm", "name": "资助", "filename": "aid"}],
    )
    monkeypatch.setattr(crawl_extra, "fetch", lambda url: "<html></html>")
    monkeypatch.setattr(crawl_extra, "parse_html", lambda html: object())
    monkeypatch.setattr(crawl_extra, "extract_title", lambda soup: "资助")
    monkeypatch.setattr(crawl_extra, "extract_main_text", lambda soup: "正文")
    monkeypatch.setattr(crawl_extra, "extract_publish_date", lambda soup: None)
    monkeypatch.setattr(crawl_extra, "acquire_html_resources", lambda *args: records, raising=False)
    monkeypatch.setattr(crawl_extra, "write_resource_manifest", lambda *args: None, raising=False)
    monkeypatch.setattr(crawl_extra, "save_raw", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_extra, "save_cleaned", lambda *args, **kwargs: None)
    monkeypatch.setattr(crawl_extra, "save_metadata", lambda *args, **kwargs: None)

    result = crawl_extra.crawl_xsc_contacts()

    assert result[0]["download_items"] == records


def test_document_link_detection_accepts_download_endpoints_and_rejects_detail_pages():
    assert is_document_link("https://example.edu/files/form.pdf")
    assert is_document_link(
        "https://example.edu/system/_content/download.jsp?file=123",
        "学生证申请表.docx",
    )
    assert not is_document_link(
        "https://example.edu/info/1099/4092.htm", "学生证申请表"
    )


def test_file_type_inference_uses_url_or_label():
    assert infer_file_type("https://example.edu/files/form.pdf") == "pdf"
    assert infer_file_type(
        "https://example.edu/system/_content/download.jsp?file=123",
        "学生证申请表.docx",
    ) == "docx"
    assert infer_file_type("https://example.edu/info/1099/4092.htm", "申请表") is None


def test_resource_extraction_keeps_detail_and_direct_links_but_ignores_navigation():
    html = """
    <a href="/">首页</a>
    <a href="/info/1099/4092.htm">学生证申请表</a>
    <a href="/system/_content/download.jsp?file=123">学生证申请表.docx</a>
    <a href="https://other.example.com/files/other.pdf">外部资料.pdf</a>
    """

    links = extract_resource_links(html, "https://jwc.example.edu/jwfw/xsxz.htm")

    assert [item["kind"] for item in links] == ["detail", "direct"]
    assert links[0]["url"] == "https://jwc.example.edu/info/1099/4092.htm"
    assert links[1]["file_type"] == "docx"


def test_pagination_extraction_stays_on_same_host_and_section():
    html = """
    <a href="/jwfw/xsxz/1.htm">下一页</a>
    <a href="/jwfw/xsxz/2.htm">2</a>
    <a href="https://other.example.com/3.htm">外部</a>
    <a href="/news/1.htm">新闻</a>
    """

    links = extract_pagination_links(html, "https://jwc.example.edu/jwfw/xsxz.htm")

    assert links == [
        "https://jwc.example.edu/jwfw/xsxz/1.htm",
        "https://jwc.example.edu/jwfw/xsxz/2.htm",
    ]


def test_metadata_record_has_canonical_download_fields():
    record = build_metadata_record(
        name="学生证申请表.docx",
        url="https://example.edu/files/form.docx",
        source_page_url="https://example.edu/downloads.htm",
        file_type="docx",
    )

    assert record == {
        "name": "学生证申请表.docx",
        "url": "https://example.edu/files/form.docx",
        "source_page_url": "https://example.edu/downloads.htm",
        "file_type": "docx",
        "status": "discovered",
        "local_path": "",
        "error": "",
    }


def test_download_public_resource_rejects_html_challenge(monkeypatch, resource_tmp_path):
    import crawler.resource_download as resource_download

    class Response:
        headers = {"content-type": "text/html"}
        content = b"<html>captcha</html>"

    monkeypatch.setattr(resource_download, "DATA_RAW_DIR", resource_tmp_path / "raw")
    monkeypatch.setattr(resource_download, "_fetch", lambda *args, **kwargs: Response())

    result = resource_download.download_public_resource(
        build_metadata_record(
            name="申请表.pdf",
            url="https://example.edu/download.jsp?id=1",
            source_page_url="https://example.edu/info/1.htm",
            file_type="pdf",
        ),
        "jwc",
    )

    assert result["status"] == "failed"
    assert "HTML" in result["error"]
    assert not [path for path in (resource_tmp_path / "raw").rglob("*") if path.is_file()]


def test_listing_acquisition_records_page_and_detail_failures(monkeypatch):
    import crawler.resource_download as resource_download

    start_url = "https://example.edu/list.htm"
    detail_url = "https://example.edu/info/1.htm"
    monkeypatch.setattr(
        resource_download,
        "discover_resource_pages",
        lambda *args, **kwargs: [
            {
                "url": start_url,
                "links": [
                    {
                        "kind": "detail",
                        "name": "申请表",
                        "url": detail_url,
                        "file_type": "",
                    }
                ],
            },
            {"url": "https://example.edu/list/2.htm", "links": [], "error": "403"},
        ],
    )
    monkeypatch.setattr(
        resource_download,
        "_fetch",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("detail timeout")),
    )

    result = resource_download.acquire_listing_resources(start_url, "jwc")

    assert {item["status"] for item in result} == {"failed"}
    assert any("detail timeout" in item["error"] for item in result)
    assert any("403" in item["error"] for item in result)
