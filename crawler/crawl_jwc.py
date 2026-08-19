"""采集教务部信息。

采集范围：
- 本科专业目录（https://jwc.zhku.edu.cn/info/1094/5377.htm）
- 2024 版培养方案入口（https://jwc.zhku.edu.cn/xsfw/pyfa2024.htm）
- 培养方案附件页（https://jwc.zhku.edu.cn/info/1991/28582.htm）
- 教务资料下载（https://jwc.zhku.edu.cn/jwfw/jwzlxz.htm）
- 学生下载（https://jwc.zhku.edu.cn/jwfw/jwzlxz/xsxz.htm）
"""
from __future__ import annotations

from typing import Any

from crawler.resource_download import (
    acquire_html_resources,
    acquire_listing_resources,
    write_resource_manifest,
)

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


def crawl_major_catalog() -> dict[str, Any]:
    """采集本科专业目录。"""
    url = "https://jwc.zhku.edu.cn/info/1094/5377.htm"
    html = fetch(url)
    soup = parse_html(html)
    title = extract_title(soup)
    text = extract_main_text(soup)
    publish_date = extract_publish_date(soup)
    attachments = extract_attachments(soup, base_url=url)
    download_items = acquire_html_resources(html, url, "jwc")
    write_resource_manifest("jwc", download_items)
    save_raw("jwc", "major_catalog.html", html)
    save_cleaned("jwc", "major_catalog.txt", text)
    metadata = {
        "url": url,
        "title": title,
        "department": "教务部",
        "publish_date": publish_date,
        "attachments": attachments,
        "download_items": download_items,
    }
    save_metadata("jwc", "major_catalog.json", metadata)
    return metadata


def crawl_training_plan_page() -> dict[str, Any]:
    """采集培养方案入口页。"""
    url = "https://jwc.zhku.edu.cn/xsfw/pyfa2024.htm"
    html = fetch(url)
    soup = parse_html(html)
    title = extract_title(soup)
    text = extract_main_text(soup)
    attachments = extract_attachments(soup, base_url=url)
    save_raw("jwc", "pyfa2024.html", html)
    save_cleaned("jwc", "pyfa2024.txt", text)
    metadata = {
        "url": url,
        "title": title,
        "department": "教务部",
        "attachments": attachments,
    }
    save_metadata("jwc", "pyfa2024.json", metadata)
    return metadata


def crawl_student_downloads() -> list[dict[str, Any]]:
    """采集学生下载栏目。

    返回每条资料的元数据列表。
    """
    url = "https://jwc.zhku.edu.cn/jwfw/jwzlxz/xsxz.htm"
    resources = acquire_listing_resources(url, "jwc")
    write_resource_manifest("jwc", resources)
    save_metadata(
        "jwc",
        "xsxz.json",
        {
            "url": url,
            "title": "学生下载",
            "department": "教务部",
            "download_items": resources,
        },
    )
    return resources


def main() -> None:
    print("[crawl_jwc] 开始采集教务部 ...")
    major = crawl_major_catalog()
    print(f"  - 本科专业目录: {major['title']}")
    plan = crawl_training_plan_page()
    print(f"  - 培养方案入口: {plan['title']}")
    downloads = crawl_student_downloads()
    print(f"  - 学生下载条目数: {len(downloads)}")
    print("[crawl_jwc] 完成")


if __name__ == "__main__":
    main()
