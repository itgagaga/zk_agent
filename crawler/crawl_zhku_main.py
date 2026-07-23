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


def crawl_school_profile() -> dict[str, Any]:
    """采集学校概况页。"""
    url = "https://www.zhku.edu.cn/xxgk.htm"
    html = fetch(url)
    soup = parse_html(html)

    title = extract_title(soup)
    text = extract_main_text(soup)
    publish_date = extract_publish_date(soup)
    attachments = extract_attachments(soup, base_url=url)

    save_raw("zhku_main", "xxgk.html", html)
    save_cleaned("zhku_main", "xxgk.txt", text)
    metadata = {
        "url": url,
        "title": title,
        "publish_date": publish_date,
        "department": "学校主站",
        "attachments": attachments,
    }
    save_metadata("zhku_main", "xxgk.json", metadata)
    return metadata


def crawl_organizations() -> dict[str, Any]:
    """采集机构设置页。"""
    url = "https://www.zhku.edu.cn/jgsz.htm"
    html = fetch(url)
    soup = parse_html(html)

    title = extract_title(soup)
    text = extract_main_text(soup)
    attachments = extract_attachments(soup, base_url=url)

    save_raw("zhku_main", "jgsz.html", html)
    save_cleaned("zhku_main", "jgsz.txt", text)
    metadata = {
        "url": url,
        "title": title,
        "department": "学校主站",
        "attachments": attachments,
    }
    save_metadata("zhku_main", "jgsz.json", metadata)
    return metadata


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
