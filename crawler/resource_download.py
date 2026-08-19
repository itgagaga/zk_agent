"""发现、解析并下载公开资料附件。"""
from __future__ import annotations

import json
import hashlib
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from backend.config import settings
from crawler.common import DATA_METADATA_DIR, DATA_RAW_DIR

DOCUMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar")
DOWNLOAD_ENDPOINT_MARKERS = ("download", "attachment", "attach")
DETAIL_PATH_MARKERS = ("/info/", "/detail")
PAGINATION_TEXT = ("下一页", "下页", "尾页", "next", "last", "上一页", "上页", "prev")


def infer_file_type(url: str, label: str = "") -> str | None:
    """从 URL 或链接文本推断文件类型。"""
    for value in (urlparse(url).path, unquote(label)):
        suffix = Path(value).suffix.lower().lstrip(".")
        if f".{suffix}" in DOCUMENT_EXTENSIONS:
            return suffix
    return None


def is_document_link(url: str, label: str = "") -> bool:
    """判断链接是否指向公开文档，而不是普通详情页。"""
    parsed = urlparse(url)
    path = parsed.path.lower()
    if path.endswith(DOCUMENT_EXTENSIONS):
        return True
    has_download_marker = any(marker in path for marker in DOWNLOAD_ENDPOINT_MARKERS)
    return has_download_marker


def _is_detail_link(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    if any(marker in path for marker in DETAIL_PATH_MARKERS):
        return True
    return path.endswith((".htm", ".html")) and bool(parsed.query)


def _same_host(left: str, right: str) -> bool:
    return urlparse(left).netloc.lower() == urlparse(right).netloc.lower()


def extract_resource_links(html: str, base_url: str) -> list[dict[str, str]]:
    """提取当前页面上的直接附件和详情页候选链接。"""
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        label = anchor.get_text(" ", strip=True)
        if not label:
            continue
        url = urljoin(base_url, str(anchor["href"]).strip())
        if not _same_host(url, base_url) or url in seen:
            continue
        if is_document_link(url, label):
            kind = "direct"
        elif _is_detail_link(url):
            kind = "detail"
        else:
            continue
        seen.add(url)
        results.append(
            {
                "kind": kind,
                "name": label,
                "url": url,
                "file_type": infer_file_type(url, label) or "",
            }
        )
    return results


def extract_pagination_links(html: str, base_url: str) -> list[str]:
    """提取当前栏目内的分页链接，避免跳到其他栏目。"""
    soup = BeautifulSoup(html, "lxml")
    base = urlparse(base_url)
    base_path = base.path.rstrip("/")
    section_prefix = base_path.rsplit("/", 1)[0] + "/"
    results: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        url = urljoin(base_url, str(anchor["href"]).strip())
        parsed = urlparse(url)
        if not _same_host(url, base_url) or url in seen:
            continue
        text = anchor.get_text(" ", strip=True).lower()
        path = parsed.path.rstrip("/")
        is_numbered_page = (
            path.startswith(section_prefix)
            and re.search(r"/\d+\.html?$", path) is not None
        )
        is_named_page = any(token in text for token in PAGINATION_TEXT)
        if not (is_numbered_page or is_named_page):
            continue
        if not (path.startswith(section_prefix) or path == base_path):
            continue
        seen.add(url)
        results.append(url)
    return results


def build_metadata_record(
    *,
    name: str,
    url: str,
    source_page_url: str,
    file_type: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "url": url,
        "source_page_url": source_page_url,
        "file_type": file_type or infer_file_type(url, name) or "",
        "status": "discovered",
        "local_path": "",
        "error": "",
    }


def normalize_download_items(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """兼容历史 metadata 中的 download_items/resources/attachments 字段。"""
    raw_items = (
        meta.get("download_items")
        or meta.get("resources")
        or meta.get("attachments")
        or []
    )
    if isinstance(raw_items, dict):
        raw_items = list(raw_items.values())
    normalized: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("title") or item.get("filename") or ""
        url = item.get("url") or item.get("file_url") or ""
        if not name or not url:
            continue
        normalized.append(
            {
                **item,
                "name": name,
                "url": url,
                "source_page_url": (
                    item.get("source_page_url")
                    or item.get("source_url")
                    or meta.get("source_url")
                    or meta.get("url")
                    or ""
                ),
                "file_type": item.get("file_type") or infer_file_type(url, name) or "",
            }
        )
    return normalized


def _fetch(
    url: str,
    *,
    binary: bool,
    retries: int = 2,
    referer: str = "",
) -> requests.Response:
    headers = {"User-Agent": settings.crawl_user_agent}
    if referer:
        headers["Referer"] = referer
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=settings.crawl_timeout)
            response.raise_for_status()
            if not binary:
                response.encoding = response.apparent_encoding or "utf-8"
            time.sleep(settings.crawl_delay)
            return response
        except Exception as error:
            last_error = error
            if attempt < retries:
                time.sleep(settings.crawl_delay * (attempt + 1))
    assert last_error is not None
    raise last_error


def discover_resource_pages(start_url: str, *, max_pages: int = 50) -> list[dict[str, Any]]:
    """抓取一个栏目及其分页，返回页面 HTML 与资源候选。"""
    queue = [start_url]
    seen: set[str] = set()
    pages: list[dict[str, Any]] = []
    while queue and len(pages) < max_pages:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            html = _fetch(url, binary=False).text
        except Exception as error:
            pages.append({"url": url, "links": [], "pagination": [], "error": str(error)})
            continue
        pagination = extract_pagination_links(html, url)
        pages.append(
            {
                "url": url,
                "html": html,
                "links": extract_resource_links(html, url),
                "pagination": pagination,
            }
        )
        queue.extend(link for link in pagination if link not in seen)
    return pages


def _safe_filename(name: str, url: str, file_type: str) -> str:
    candidate = Path(unquote(name)).name.strip()
    candidate = re.sub(r"[^\w\u4e00-\u9fff.() -]+", "_", candidate).strip(" .")
    if not candidate:
        candidate = Path(urlparse(url).path).name or "resource"
    if file_type and Path(candidate).suffix.lower() in {".jsp", ".php", ".htm", ".html"}:
        candidate = Path(candidate).stem
    if file_type and not Path(candidate).suffix:
        candidate = f"{candidate}.{file_type}"
    # Multiple public pages on the graduate site use the same display name
    # (for example, "下载地址.doc"). Keep the readable name but append a
    # stable URL digest so different resources cannot overwrite each other.
    path = Path(candidate)
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    candidate = f"{path.stem}_{digest}{path.suffix}"
    return candidate[:180]


def _file_type_from_content_type(content_type: str) -> str:
    lower = content_type.lower()
    mappings = {
        "pdf": "pdf",
        "msword": "doc",
        "wordprocessingml": "docx",
        "msexcel": "xls",
        "spreadsheetml": "xlsx",
        "zip": "zip",
        "rar": "rar",
    }
    for marker, file_type in mappings.items():
        if marker in lower:
            return file_type
    return ""


def download_public_resource(
    resource: dict[str, Any],
    source_dir: str,
    *,
    retries: int = 2,
) -> dict[str, Any]:
    """下载一个公开附件，并把失败原因写回记录。"""
    record = dict(resource)
    target_dir = DATA_RAW_DIR / source_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        response = _fetch(
            str(record["url"]),
            binary=True,
            retries=retries,
            referer=str(record.get("source_page_url", "")),
        )
        content = response.content
        content_type = (response.headers.get("content-type") or "").lower()
        head = content[:512].lower()
        is_html = "text/html" in content_type or head.startswith((b"<html", b"<!doctype"))
        if is_html:
            raise ValueError("返回内容是 HTML 页面或验证页面，不是文件")
        file_type = str(record.get("file_type", "")) or _file_type_from_content_type(
            content_type
        )
        record["file_type"] = file_type
        filename = _safe_filename(
            str(record.get("name", "")),
            str(record.get("url", "")),
            file_type,
        )
        target = target_dir / filename
        target.write_bytes(content)
        record["status"] = "downloaded"
        record["local_path"] = str(target.relative_to(DATA_RAW_DIR.parent.parent)).replace("\\", "/")
        record["error"] = ""
    except Exception as error:
        record["status"] = "failed"
        record["local_path"] = ""
        record["error"] = str(error)
    return record


def acquire_listing_resources(
    start_url: str,
    source_dir: str,
    *,
    max_pages: int = 50,
    max_detail_pages: int = 200,
) -> list[dict[str, Any]]:
    """从列表页、分页和详情页发现并下载附件。"""
    pages = discover_resource_pages(start_url, max_pages=max_pages)
    direct: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    detail_queue: list[dict[str, str]] = []
    for page in pages:
        if page.get("error"):
            failure = build_metadata_record(
                name=f"页面采集失败: {page['url']}",
                url=page["url"],
                source_page_url=page["url"],
            )
            failure["status"] = "failed"
            failure["error"] = str(page["error"])
            failures.append(failure)
        for link in page.get("links", []):
            if link["kind"] == "direct":
                direct.setdefault(
                    link["url"],
                    build_metadata_record(
                        name=link["name"],
                        url=link["url"],
                        source_page_url=page["url"],
                        file_type=link.get("file_type", ""),
                    ),
                )
            else:
                detail_queue.append({**link, "source_page_url": page["url"]})

    for detail in detail_queue[:max_detail_pages]:
        try:
            html = _fetch(detail["url"], binary=False).text
        except Exception as error:
            failure = build_metadata_record(
                name=f"详情页采集失败: {detail['name']}",
                url=detail["url"],
                source_page_url=detail["source_page_url"],
            )
            failure["status"] = "failed"
            failure["error"] = str(error)
            failures.append(failure)
            continue
        for link in extract_resource_links(html, detail["url"]):
            if link["kind"] != "direct":
                continue
            direct.setdefault(
                link["url"],
                build_metadata_record(
                    name=link["name"],
                    url=link["url"],
                    source_page_url=detail["url"],
                    file_type=link.get("file_type", ""),
                ),
            )

    return failures + [download_public_resource(item, source_dir) for item in direct.values()]


def acquire_html_resources(
    html: str,
    source_page_url: str,
    source_dir: str,
) -> list[dict[str, Any]]:
    """从已经获取的详情页 HTML 中下载直接附件。"""
    records: list[dict[str, Any]] = []
    for link in extract_resource_links(html, source_page_url):
        if link["kind"] != "direct":
            continue
        records.append(
            download_public_resource(
                build_metadata_record(
                    name=link["name"],
                    url=link["url"],
                    source_page_url=source_page_url,
                    file_type=link.get("file_type", ""),
                ),
                source_dir,
            )
        )
    return records


def acquire_page_resources(
    page_url: str,
    source_dir: str,
) -> list[dict[str, Any]]:
    """获取一个公开详情页并下载其直接附件。"""
    html = _fetch(page_url, binary=False).text
    return acquire_html_resources(html, page_url, source_dir)


def write_resource_manifest(source_dir: str, records: list[dict[str, Any]]) -> Path:
    target_dir = DATA_METADATA_DIR / source_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "resource_manifest.json"
    previous: list[dict[str, Any]] = []
    if target.exists():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                previous = [item for item in loaded if isinstance(item, dict)]
        except Exception:
            previous = []
    merged: dict[str, dict[str, Any]] = {
        str(item.get("url")): item for item in previous if item.get("url")
    }
    merged.update({str(item.get("url")): item for item in records if item.get("url")})
    target.write_text(
        json.dumps(list(merged.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target
