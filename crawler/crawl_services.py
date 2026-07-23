"""采集公共服务模块信息。

采集范围：
- 总务后勤部（https://hqyzc.zhku.edu.cn/）
  - 联系方式（https://hqyzc.zhku.edu.cn/bmgk/lxwm.htm）
  - 交通车、物业、膳食通知
- 现代教育技术中心（https://wlzx.zhku.edu.cn/）
  - 网络报障、邮箱、VPN、多媒体教室
- 校医院（https://xys.zhku.edu.cn/）
  - 就医指引（https://xys.zhku.edu.cn/info/1180/1542.htm）
  - 医药费报销审核（https://xys.zhku.edu.cn/info/1160/1322.htm）
"""
from __future__ import annotations

from typing import Any

from crawler.common import (
    extract_main_text,
    extract_publish_date,
    extract_title,
    fetch,
    parse_html,
    save_cleaned,
    save_metadata,
    save_raw,
)


def crawl_logistics_contacts() -> dict[str, Any]:
    """采集后勤联系方式页。"""
    url = "https://hqyzc.zhku.edu.cn/bmgk/lxwm.htm"
    html = fetch(url)
    soup = parse_html(html)
    title = extract_title(soup)
    text = extract_main_text(soup)
    publish_date = extract_publish_date(soup)
    save_raw("hqyzc", "lxwm.html", html)
    save_cleaned("hqyzc", "lxwm.txt", text)
    metadata = {
        "url": url,
        "title": title,
        "department": "总务后勤部",
        "publish_date": publish_date,
    }
    save_metadata("hqyzc", "lxwm.json", metadata)
    return metadata


def crawl_it_center_services() -> dict[str, Any]:
    """采集现代教育技术中心服务指南。"""
    url = "https://wlzx.zhku.edu.cn/"
    html = fetch(url)
    soup = parse_html(html)
    title = extract_title(soup)
    text = extract_main_text(soup)
    save_raw("wlzx", "index.html", html)
    save_cleaned("wlzx", "index.txt", text)
    metadata = {"url": url, "title": title, "department": "现代教育技术中心"}
    save_metadata("wlzx", "index.json", metadata)
    return metadata


def crawl_hospital_guide() -> dict[str, Any]:
    """采集校医院就医指引。"""
    url = "https://xys.zhku.edu.cn/info/1180/1542.htm"
    html = fetch(url)
    soup = parse_html(html)
    title = extract_title(soup)
    text = extract_main_text(soup)
    publish_date = extract_publish_date(soup)
    save_raw("xys", "medical_guide.html", html)
    save_cleaned("xys", "medical_guide.txt", text)
    metadata = {
        "url": url,
        "title": title,
        "department": "校医院",
        "publish_date": publish_date,
    }
    save_metadata("xys", "medical_guide.json", metadata)
    return metadata


def crawl_hospital_reimbursement() -> dict[str, Any]:
    """采集校医院医药费报销审核说明。"""
    url = "https://xys.zhku.edu.cn/info/1160/1322.htm"
    html = fetch(url)
    soup = parse_html(html)
    title = extract_title(soup)
    text = extract_main_text(soup)
    publish_date = extract_publish_date(soup)
    save_raw("xys", "reimbursement.html", html)
    save_cleaned("xys", "reimbursement.txt", text)
    metadata = {
        "url": url,
        "title": title,
        "department": "校医院",
        "publish_date": publish_date,
    }
    save_metadata("xys", "reimbursement.json", metadata)
    return metadata


def main() -> None:
    print("[crawl_services] 开始采集公共服务模块 ...")
    logistics = crawl_logistics_contacts()
    print(f"  - 后勤联系方式: {logistics['title']}")
    it_center = crawl_it_center_services()
    print(f"  - 现代教育技术中心: {it_center['title']}")
    hospital = crawl_hospital_guide()
    print(f"  - 校医院就医指引: {hospital['title']}")
    reimbursement = crawl_hospital_reimbursement()
    print(f"  - 医药费报销审核: {reimbursement['title']}")
    print("[crawl_services] 完成")


if __name__ == "__main__":
    main()
