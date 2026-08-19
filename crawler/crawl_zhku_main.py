"""采集仲恺主站信息。

采集范围：
- 学校概况（https://www.zhku.edu.cn/xxgk.htm）
- 校区地址
- 机构设置（https://www.zhku.edu.cn/jgsz.htm）
- 主站新闻公告
- 快捷链接与服务入口
"""
from __future__ import annotations

from typing import Any

from crawler.resource_download import acquire_html_resources, write_resource_manifest

from backend.config import settings
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


ORGANIZATION_PAGES = [
    {
        "url": "https://www.zhku.edu.cn/jgsz/dzgljg_qtzuz.htm",
        "filename": "org_admin",
        "name": "党政管理机构、群团组织",
    },
    {
        "url": "https://www.zhku.edu.cn/jgsz/jxjg.htm",
        "filename": "org_teaching",
        "name": "教学机构",
    },
    {
        "url": "https://www.zhku.edu.cn/jgsz/jf_kyjgjfwpt.htm",
        "filename": "org_support_research",
        "name": "教辅、科研机构及服务平台",
    },
]


def crawl_school_profile() -> dict[str, Any]:
    """采集学校概况页。"""
    url = "https://www.zhku.edu.cn/xxgk.htm"
    html = fetch(url)
    soup = parse_html(html)

    title = extract_title(soup)
    text = extract_main_text(soup)
    publish_date = extract_publish_date(soup)
    attachments = extract_attachments(soup, base_url=url)
    download_items = acquire_html_resources(html, url, "zhku_main")
    write_resource_manifest("zhku_main", download_items)

    save_raw("zhku_main", "xxgk.html", html)
    save_cleaned("zhku_main", "xxgk.txt", text)
    metadata = {
        "url": url,
        "title": title,
        "publish_date": publish_date,
        "department": "学校主站",
        "attachments": attachments,
        "download_items": download_items,
    }
    save_metadata("zhku_main", "xxgk.json", metadata)
    return metadata


def crawl_organizations() -> dict[str, Any]:
    """采集官网当前的三个机构设置分页面。"""
    results: list[dict[str, Any]] = []
    for item in ORGANIZATION_PAGES:
        url = item["url"]
        html = fetch(url, referer="https://www.zhku.edu.cn/")
        soup = parse_html(html)

        title = extract_title(soup)
        text = extract_main_text(soup)
        attachments = extract_attachments(soup, base_url=url)
        download_items = acquire_html_resources(html, url, "zhku_main")
        write_resource_manifest("zhku_main", download_items)

        save_raw("zhku_main", f"{item['filename']}.html", html)
        save_cleaned("zhku_main", f"{item['filename']}.txt", text)
        metadata = {
            "url": url,
            "title": title or item["name"],
            "department": "学校主站",
            "attachments": attachments,
            "download_items": download_items,
        }
        save_metadata("zhku_main", f"{item['filename']}.json", metadata)
        results.append(metadata)
    return results[0]


def crawl_news_list(category: str = "学校要闻") -> list[dict[str, Any]]:
    """采集主站新闻列表。

    TODO: 实现具体栏目 URL 与分页。
    """
    return []


def main() -> None:
    """主入口：采集学校主站。"""
    print("[crawl_zhku_main] 开始采集学校主站 ...")
    profile = crawl_school_profile()
    print(f"  - 学校概况: {profile['title']}")
    orgs = crawl_organizations()
    print(f"  - 机构设置: {orgs['title']}")
    print("[crawl_zhku_main] 完成")


if __name__ == "__main__":
    main()
