"""采集学生工作部、财务部、招生网等新增模块信息。

采集范围：
- 学生工作部（https://xsc.zhku.edu.cn/）
  - 联系方式汇总（资助、宿舍报修、心理咨询、武装部等）
- 招生网（https://zsb-portal.zhku.edu.cn/）
  - 2026年本科招生简章
  - 2025年本科招生录取情况
- 研究生部（https://yjs.zhku.edu.cn/）
  - 2026年硕士研究生招生专业目录
  - 各研究生招生学院及研招办联系方式
  - 2026年硕士研究生招生复试录取办法
  - 2026年硕士研究生招生调剂说明
- 财务部（https://cwc.zhku.edu.cn/）
  - 服务指南
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_CLEANED_DIR = PROJECT_ROOT / "data" / "cleaned"
DATA_METADATA_DIR = PROJECT_ROOT / "data" / "metadata"

TODAY = str(date.today())


# ---------------------------------------------------------------------------
# 学生工作部
# ---------------------------------------------------------------------------

XSC_CONTACTS = [
    {
        "url": "https://xsc.zhku.edu.cn/info/1156/11362.htm",
        "name": "学生资助管理服务联系方式",
        "filename": "zzgl",
    },
    {
        "url": "https://xsc.zhku.edu.cn/info/1156/11332.htm",
        "name": "两校区宿舍报修流程和意见反馈渠道",
        "filename": "dorm_repair",
    },
    {
        "url": "https://xsc.zhku.edu.cn/info/1156/11322.htm",
        "name": "心理健康教育与咨询中心联系方式",
        "filename": "mental_health",
    },
    {
        "url": "https://xsc.zhku.edu.cn/info/1156/11342.htm",
        "name": "人民武装部联系方式",
        "filename": "wubu",
    },
    {
        "url": "https://xsc.zhku.edu.cn/info/1156/11312.htm",
        "name": "学生社区管理服务中心联系方式",
        "filename": "community",
    },
    {
        "url": "https://xsc.zhku.edu.cn/info/1156/11352.htm",
        "name": "就业指导中心联系方式",
        "filename": "job",
    },
]


def crawl_xsc_contacts() -> list[dict[str, Any]]:
    """采集学生工作部各联系方式页。"""
    results = []
    for item in XSC_CONTACTS:
        url = item["url"]
        try:
            html = fetch(url)
            soup = parse_html(html)
            title = extract_title(soup)
            text = extract_main_text(soup)
            publish_date = extract_publish_date(soup)

            save_raw("xsc", f"{item['filename']}.html", html)
            save_cleaned("xsc", f"{item['filename']}.txt", text)
            meta = {
                "url": url,
                "title": title,
                "department": "学生工作部",
                "publish_date": publish_date,
            }
            save_metadata("xsc", f"{item['filename']}.json", meta)
            results.append(meta)
            print(f"  - {item['name']}: {title}")
        except Exception as e:
            print(f"  - {item['name']}: 采集失败 - {e}")
    return results


# ---------------------------------------------------------------------------
# 招生网（新门户）
# ---------------------------------------------------------------------------

ZSB_PAGES = [
    {
        "url": "https://zsb-portal.zhku.edu.cn/detail?id=3214",
        "name": "2026年夏季高考招生章程",
        "filename": "bkzs_zc_2026",
    },
    {
        "url": "https://zsb-portal.zhku.edu.cn/detail?id=3206",
        "name": "2025年本科招生录取情况(广东省)",
        "filename": "bkzs_scores_2025_gd",
    },
    {
        "url": "https://zsb-portal.zhku.edu.cn/detail?id=3207",
        "name": "2025年本科招生录取情况(广东省外)",
        "filename": "bkzs_scores_2025_other",
    },
]


def crawl_zsb_portal() -> list[dict[str, Any]]:
    """采集招生网门户页面。"""
    results = []
    for item in ZSB_PAGES:
        url = item["url"]
        try:
            html = fetch(url)
            soup = parse_html(html)
            title = extract_title(soup)
            text = extract_main_text(soup)

            save_raw("zsb", f"{item['filename']}.html", html)
            save_cleaned("zsb", f"{item['filename']}.txt", text)
            meta = {
                "url": url,
                "title": title or item["name"],
                "department": "招生办公室",
            }
            save_metadata("zsb", f"{item['filename']}.json", meta)
            results.append(meta)
            print(f"  - {item['name']}: {title or item['name']}")
        except Exception as e:
            print(f"  - {item['name']}: 采集失败 - {e}")
    return results


# ---------------------------------------------------------------------------
# 研究生部（补充页面）
# ---------------------------------------------------------------------------

YJS_EXTRA_PAGES = [
    {
        "url": "https://yjs.zhku.edu.cn/info/1047/7145.htm",
        "name": "2026年硕士研究生招生专业目录",
        "filename": "major_catalog_2026",
    },
    {
        "url": "https://yjs.zhku.edu.cn/info/1047/7155.htm",
        "name": "各研究生招生学院及研招办联系方式",
        "filename": "yjs_contacts",
    },
    {
        "url": "https://yjs.zhku.edu.cn/info/1047/7425.htm",
        "name": "2026年硕士研究生招生复试录取办法",
        "filename": "fushi_2026",
    },
    {
        "url": "https://yjs.zhku.edu.cn/info/1047/7525.htm",
        "name": "2026年硕士研究生招生调剂说明",
        "filename": "tiaoji_2026",
    },
    {
        "url": "https://yjs.zhku.edu.cn/info/1047/7135.htm",
        "name": "2026年硕士研究生招生章程",
        "filename": "admission_charter_2026_full",
    },
    {
        "url": "https://yjs.zhku.edu.cn/info/1047/7545.htm",
        "name": "2026年各学院研究生招生复试及调剂事宜查询方式",
        "filename": "fushi_query_2026",
    },
]


def crawl_yjs_extra() -> list[dict[str, Any]]:
    """采集研究生部补充页面。"""
    results = []
    for item in YJS_EXTRA_PAGES:
        url = item["url"]
        try:
            html = fetch(url)
            soup = parse_html(html)
            title = extract_title(soup)
            text = extract_main_text(soup)
            publish_date = extract_publish_date(soup)

            save_raw("yjs", f"{item['filename']}.html", html)
            save_cleaned("yjs", f"{item['filename']}.txt", text)
            meta = {
                "url": url,
                "title": title or item["name"],
                "department": "研究生部",
                "publish_date": publish_date,
            }
            save_metadata("yjs", f"{item['filename']}.json", meta)
            results.append(meta)
            print(f"  - {item['name']}: {title or item['name']}")
        except Exception as e:
            print(f"  - {item['name']}: 采集失败 - {e}")
    return results


# ---------------------------------------------------------------------------
# 财务部
# ---------------------------------------------------------------------------

CWC_PAGES = [
    {
        "url": "https://cwc.zhku.edu.cn/info/1585/3927.htm",
        "name": "医疗费无纸化报账操作流程",
        "filename": "yilf_baozhang",
    },
    {
        "url": "https://cwc.zhku.edu.cn/info/1585/4257.htm",
        "name": "薪酬劳务无纸化报账指引",
        "filename": "xingchou_baozhang",
    },
    {
        "url": "https://cwc.zhku.edu.cn/info/2019/4287.htm",
        "name": "市内交通费、差旅费业务报账补充通知",
        "filename": "chailvfei",
    },
]


def crawl_cwc() -> list[dict[str, Any]]:
    """采集财务部页面。"""
    results = []
    for item in CWC_PAGES:
        url = item["url"]
        try:
            html = fetch(url)
            soup = parse_html(html)
            title = extract_title(soup)
            text = extract_main_text(soup)
            publish_date = extract_publish_date(soup)

            save_raw("cwc", f"{item['filename']}.html", html)
            save_cleaned("cwc", f"{item['filename']}.txt", text)
            meta = {
                "url": url,
                "title": title or item["name"],
                "department": "财务部",
                "publish_date": publish_date,
            }
            save_metadata("cwc", f"{item['filename']}.json", meta)
            results.append(meta)
            print(f"  - {item['name']}: {title or item['name']}")
        except Exception as e:
            print(f"  - {item['name']}: 采集失败 - {e}")
    return results


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def main() -> None:
    """主入口：采集新增模块。"""
    print("[crawl_extra] 开始采集新增模块 ...")

    print("\n  [1/4] 学生工作部")
    crawl_xsc_contacts()

    print("\n  [2/4] 招生网门户")
    crawl_zsb_portal()

    print("\n  [3/4] 研究生部（补充）")
    crawl_yjs_extra()

    print("\n  [4/4] 财务部")
    crawl_cwc()

    print("\n[crawl_extra] 完成")


if __name__ == "__main__":
    main()
