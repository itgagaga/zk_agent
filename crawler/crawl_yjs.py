"""采集研究生处信息。

采集范围：
- 研究生处首页（https://yjs.zhku.edu.cn/）
- 2026 年硕士研究生招生章程（https://yjs.zhku.edu.cn/info/1047/7135.htm）
- 研究生培养学生下载（https://yjs.zhku.edu.cn/xgxz/yjspy_xsxzl_.htm）
"""
from __future__ import annotations

from typing import Any

from crawler.common import (
    extract_attachments,
    extract_main_text,
    extract_publish_date,
    extract_title,
    fetch,
    parse_html,
    save_cleaned,
    save_metadata,
    save_raw,
)


def crawl_graduate_admission_charter() -> dict[str, Any]:
    """采集研究生招生章程。"""
    url = "https://yjs.zhku.edu.cn/info/1047/7135.htm"
    html = fetch(url)
    soup = parse_html(html)
    title = extract_title(soup)
    text = extract_main_text(soup)
    publish_date = extract_publish_date(soup)
    attachments = extract_attachments(soup, base_url=url)
    save_raw("yjs", "admission_charter.html", html)
    save_cleaned("yjs", "admission_charter.txt", text)
    metadata = {
        "url": url,
        "title": title,
        "department": "研究生处",
        "publish_date": publish_date,
        "attachments": attachments,
    }
    save_metadata("yjs", "admission_charter.json", metadata)
    return metadata


def crawl_graduate_downloads() -> list[dict[str, Any]]:
    """采集研究生培养学生下载栏。"""
    url = "https://yjs.zhku.edu.cn/xgxz/yjspy_xsxzl_.htm"
    html = fetch(url)
    soup = parse_html(html)
    save_raw("yjs", "graduate_downloads.html", html)

    resources: list[dict[str, Any]] = []
    for a in soup.find_all("a", href=True):
        name = a.get_text(strip=True)
        href = a["href"]
        if not name or not href.lower().endswith(
            (".doc", ".docx", ".pdf", ".xls", ".xlsx", ".zip", ".rar")
        ):
            continue
        from urllib.parse import urljoin

        resources.append(
            {
                "title": name,
                "category": "研究生培养",
                "audience": "研究生",
                "file_type": href.lower().rsplit(".", 1)[-1],
                "source_page_url": url,
                "file_url": urljoin(url, href),
                "department": "研究生处",
            }
        )

    save_metadata(
        "yjs",
        "graduate_downloads.json",
        {"url": url, "department": "研究生处", "resources": resources},
    )
    return resources


def main() -> None:
    print("[crawl_yjs] 开始采集研究生处 ...")
    charter = crawl_graduate_admission_charter()
    print(f"  - 招生章程: {charter['title']}")
    downloads = crawl_graduate_downloads()
    print(f"  - 研究生下载条目数: {len(downloads)}")
    print("[crawl_yjs] 完成")


if __name__ == "__main__":
    main()
