"""采集就业指导中心的公开职位和招聘活动信息。

只访问无需登录的公开页面；就业新闻仍不在采集范围内。
"""
from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from backend.config import settings
from crawler.common import (
    DATA_CLEANED_DIR,
    extract_main_text,
    fetch,
    parse_html,
    save_cleaned,
    save_metadata,
    save_raw,
)

JOB_BASE_URL = settings.zhku_job_url.rstrip("/")
JOB_LIST_URL = f"{JOB_BASE_URL}/web/index/job-list"
PREACH_LIST_URL = f"{JOB_BASE_URL}/web/index/preach-list"
JOBFAIR_LIST_URL = f"{JOB_BASE_URL}/web/index/jobfair-list"


def _text(node: Any) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def _absolute_url(href: str, base_url: str) -> str:
    url = urljoin(base_url, href)
    parsed = urlparse(url)
    if parsed.netloc.lower() == urlparse(base_url).netloc.lower():
        url = url.replace("http://", "https://", 1)
    return url


def _id_from_url(url: str) -> str:
    return parse_qs(urlparse(url).query).get("id", [""])[0]


def _parse_job_cards(html: str, source_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, Any]] = []
    for card in soup.select("a.job-block[href*='job-detail']"):
        url = _absolute_url(str(card["href"]), source_url)
        industry_values = [_text(node) for node in card.select(".job-industry")]
        item = {
            "id": _id_from_url(url),
            "name": _text(card.select_one(".job-name")),
            "published": _text(card.select_one(".job-time")),
            "company": _text(card.select_one(".job-company")),
            "salary": _text(card.select_one(".job-salary")),
            "education": _text(card.select_one(".job-edu")),
            "industry": industry_values[0] if industry_values else "",
            "location": industry_values[-1] if len(industry_values) > 1 else "",
            "benefits": _text(card.select_one(".third-line")),
            "url": url,
            "source_url": source_url,
            "status": "discovered",
            "error": "",
        }
        if item["url"] not in {existing["url"] for existing in results}:
            results.append(item)
    return results


def _parse_recruitment_events(html: str, source_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, Any]] = []
    anchors = soup.find_all("a", href=re.compile(r"(?:preach|jobfair)-detail"))
    for anchor in anchors:
        url = _absolute_url(str(anchor["href"]), source_url)
        title = _text(anchor.select_one(".title, .preach-name"))
        time_text = _text(anchor.select_one(".preach-time"))
        location = _text(anchor.select_one(".preach-address"))
        company = _text(anchor.select_one(".preach-company"))
        text_nodes = [_text(node) for node in anchor.select(".list-content-block .text")]
        if not time_text and text_nodes:
            time_text = text_nodes[0]
        if not location and len(text_nodes) > 1:
            location = text_nodes[1]
        if not company and len(text_nodes) > 2:
            company = text_nodes[2]
        if not title:
            title = _text(anchor.select_one("img[alt]"))
            if not title:
                image = anchor.select_one("img[alt]")
                title = str(image.get("alt", "")) if image else ""
        item = {
            "id": _id_from_url(url),
            "name": title,
            "time": time_text,
            "location": location,
            "company": company,
            "url": url,
            "source_url": source_url,
            "status": "discovered",
            "error": "",
        }
        if item["url"] not in {existing["url"] for existing in results}:
            results.append(item)
    return results


def _detail_path(kind: str, item_id: str) -> str:
    return f"data/cleaned/job/{kind}_{item_id}.txt"


def _fetch_detail(item: dict[str, Any], kind: str) -> None:
    try:
        html = fetch(item["url"], referer=item["source_url"])
        item["detail_path"] = _detail_path(kind, item["id"] or "unknown")
        save_raw("job", f"{kind}_{item['id'] or 'unknown'}.html", html)
        text = extract_main_text(parse_html(html))
        save_cleaned("job", f"{kind}_{item['id'] or 'unknown'}.txt", text)
        item["status"] = "downloaded"
    except Exception as error:
        item["status"] = "detail_failed"
        item["error"] = str(error)


def write_detail_metadata(
    items: list[dict[str, Any]], kind: Literal["job", "event"]
) -> int:
    """为已下载的职位/活动详情写入与正文同名的 metadata。"""
    if kind not in {"job", "event"}:
        raise ValueError(f"unsupported employment detail kind: {kind}")

    written = 0
    is_event = kind == "event"
    for item in items:
        item_id = str(item.get("id") or "").strip()
        if item.get("status") != "downloaded" or not item_id:
            continue
        save_metadata(
            "job",
            f"{kind}_{item_id}.json",
            {
                "id": item_id,
                "title": item.get("name") or f"就业详情 {item_id}",
                "company": item.get("company") or "",
                "source_url": item.get("url") or "",
                "publish_date": (
                    item.get("time") if is_event else item.get("published", "")
                ),
                "category": "就业与招聘",
                "subcategory": "校园招聘活动" if is_event else "公开职位",
                "audience": "毕业生/求职者",
                "document_type": "招聘活动" if is_event else "职位详情",
            },
        )
        written += 1
    return written


def crawl_job_postings(top_k: int = 100) -> list[dict[str, Any]]:
    """采集公开职位列表及前 ``top_k`` 条职位详情。"""
    if top_k <= 0:
        return []
    jobs: list[dict[str, Any]] = []
    pages: list[str] = []
    page = 1
    while len(jobs) < top_k and page <= 20:
        url = JOB_LIST_URL if page == 1 else f"{JOB_BASE_URL}/index.php/web/index/job-list?p={page}"
        try:
            html = fetch(url, referer=JOB_LIST_URL)
        except Exception as error:
            jobs.append(
                {
                    "name": f"职位列表第 {page} 页",
                    "url": url,
                    "source_url": JOB_LIST_URL,
                    "status": "list_failed",
                    "error": str(error),
                }
            )
            break
        pages.append(url)
        save_raw("job", f"job_list_{page}.html", html)
        for item in _parse_job_cards(html, url):
            if item["url"] not in {existing["url"] for existing in jobs}:
                jobs.append(item)
                if len(jobs) >= top_k:
                    break
        if not _parse_job_cards(html, url):
            break
        page += 1

    for item in jobs:
        if item.get("status") == "discovered":
            _fetch_detail(item, "job")
    write_detail_metadata(jobs, "job")
    save_metadata(
        "job",
        "job_postings.json",
        {"url": JOB_LIST_URL, "pages": pages, "count": len(jobs), "items": jobs},
    )
    return jobs


def crawl_job_fairs() -> list[dict[str, Any]]:
    """采集公开的校园宣讲会/招聘会列表及详情。"""
    events: list[dict[str, Any]] = []
    pages = []
    for kind, url in (("preach", PREACH_LIST_URL), ("jobfair", JOBFAIR_LIST_URL)):
        try:
            html = fetch(url, referer=JOB_BASE_URL + "/")
        except Exception as error:
            events.append(
                {
                    "name": kind,
                    "url": url,
                    "source_url": url,
                    "status": "list_failed",
                    "error": str(error),
                }
            )
            continue
        pages.append(url)
        save_raw("job", f"{kind}_list.html", html)
        for item in _parse_recruitment_events(html, url):
            if item["url"] not in {existing["url"] for existing in events}:
                events.append(item)

    for item in events:
        if item.get("status") == "discovered":
            _fetch_detail(item, "event")
    write_detail_metadata(events, "event")
    save_metadata(
        "job",
        "job_fairs.json",
        {"pages": pages, "count": len(events), "items": events},
    )
    return events


def main() -> None:
    print("[crawl_job] 开始采集就业指导中心 ...")
    jobs = crawl_job_postings()
    print(f"  - 职位条目数: {len(jobs)}")
    events = crawl_job_fairs()
    print(f"  - 宣讲会/招聘会条目数: {len(events)}")
    print("[crawl_job] 完成")


if __name__ == "__main__":
    main()
