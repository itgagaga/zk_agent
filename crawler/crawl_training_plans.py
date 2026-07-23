"""采集 2024 版本科专业人才培养方案 PDF。

来源页面：https://jwc.zhku.edu.cn/info/1991/28582.htm
该页面以附件形式列出全部专业的培养方案 PDF（63 份左右）。

本模块逐一下载 PDF → 解析文本 → 写入 data/cleaned/jwc/ 与 data/metadata/jwc/，
供 build_kb.py 切分向量化后供 RAG 检索。
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from backend.config import settings
from crawler.common import save_cleaned, save_metadata, save_raw
from crawler.parse_documents import parse_pdf

# 培养方案列表页
PLAN_LIST_URL = "https://jwc.zhku.edu.cn/info/1991/28582.htm"
# 列表页本身的发布时间（页面显示 2025-02-24）
PLAN_PUBLISH_DATE = "2025-02-24"


def _fetch_html(url: str) -> str:
    """获取页面 HTML。"""
    headers = {"User-Agent": settings.crawl_user_agent}
    resp = requests.get(url, headers=headers, timeout=settings.crawl_timeout)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def _fetch_bytes(url: str) -> bytes:
    """下载二进制内容（PDF）。"""
    headers = {"User-Agent": settings.crawl_user_agent}
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.content


def _parse_plan_links(html: str) -> list[dict[str, str]]:
    """从列表页 HTML 中提取培养方案 PDF 链接。

    返回每一项：{name, url, major_code, major_name, file_type}
    """
    soup = BeautifulSoup(html, "lxml")
    items: list[dict[str, str]] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        name = a.get_text(strip=True)
        if not name:
            continue
        lower_href = href.lower()
        lower_name = name.lower()
        # 仲恺教务部附件下载链接形如 download.jsp?urltype=...，文件名在锚文本里
        is_download_link = "download.jsp" in lower_href
        is_pdf_name = lower_name.endswith(".pdf")
        if not (is_download_link and is_pdf_name):
            continue
        abs_url = urljoin(PLAN_LIST_URL, href)
        if abs_url in seen:
            continue
        seen.add(abs_url)

        code, major_name = _parse_major_from_name(name)
        items.append(
            {
                "name": name,
                "url": abs_url,
                "major_code": code,
                "major_name": major_name,
                "file_type": "pdf",
            }
        )
    return items


def _parse_major_from_name(raw: str) -> tuple[str, str]:
    """从附件名中解析专业代码与专业名称。

    样例：
      "1.090101 农学人才培养方案.pdf"        -> ("090101", "农学")
      "11.食品科学与工程（国际班）人才培养方案.pdf" -> ("", "食品科学与工程（国际班）")
      "57.土木工程（国际班）人才培养方案.pdf"      -> ("", "土木工程（国际班）")
    """
    # 去掉扩展名
    stem = re.sub(r"\.pdf$", "", raw, flags=re.IGNORECASE)
    # 去掉前缀序号 "1." / "11." 等
    stem = re.sub(r"^\d+\.", "", stem)
    # 去掉尾部 "人才培养方案"
    stem = re.sub(r"人才培养方案\s*$", "", stem).strip()

    # 尝试匹配开头为专业代码（数字+可能的字母 T/K）
    m = re.match(r"^(\d+[A-Z]*T*K*)\s+(.+)$", stem)
    if m:
        return m.group(1), m.group(2).strip()
    return "", stem


def _sanitize_filename(name: str) -> str:
    """生成安全的文件名 stem。"""
    # 保留中文、字母、数字、括号；其余替换为下划线
    safe = re.sub(r"[^\w\u4e00-\u9fff（）()]+", "_", name).strip("_")
    return safe or "unknown"


def _build_text_header(item: dict[str, str]) -> str:
    """为解析后的 PDF 文本加上结构化头部，提升检索召回。"""
    code = item.get("major_code", "")
    name = item.get("major_name", "")
    lines = [
        f"专业名称：{name}",
    ]
    if code:
        lines.insert(0, f"专业代码：{code}")
    lines.append("文档类型：2024版本科专业人才培养方案")
    lines.append("来源：仲恺农业工程学院教务部")
    lines.append("")
    return "\n".join(lines)


def _looks_like_captcha(data: bytes) -> bool:
    """判断下载到的内容是否为验证码 HTML 页面而非真实 PDF。

    真实 PDF 以 '%PDF-' 开头；仲恺教务部下载.jsp 在未通过验证码时会
    返回 HTML 页面（'<!DOCTYPE html>' 或 '<html'），提示"请输入验证码下载附件"。
    """
    if data[:5] == b"%PDF-":
        return False
    head = data[:200].lower()
    if head.startswith(b"<!doctype") or head.startswith(b"<html"):
        return True
    # 验证码页面包含中文"验证码"
    try:
        return "验证码" in data[:2048].decode("utf-8", errors="ignore")
    except Exception:
        return False


def _build_index_document(links: list[dict[str, str]]) -> str:
    """构建培养方案总索引文档（Markdown）。

    无论 PDF 是否下载成功，都生成此索引，确保 RAG 能回答
    "有哪些培养方案 / 某专业的培养方案链接" 类问题。
    """
    lines = [
        "仲恺农业工程学院 2024 版本科专业人才培养方案 总览",
        "",
        f"来源：{PLAN_LIST_URL}",
        f"发布时间：{PLAN_PUBLISH_DATE}",
        f"发布部门：教务部",
        f"共收录 {len(links)} 份专业培养方案，列表如下：",
        "",
        "| 序号 | 专业代码 | 专业名称 | 培养方案链接 |",
        "| --- | --- | --- | --- |",
    ]
    for i, item in enumerate(links, 1):
        code = item.get("major_code", "—")
        name = item.get("major_name", item["name"])
        lines.append(f"| {i} | {code} | {name} | {item['url']} |")
    lines.append("")
    lines.append("说明：以上每份培养方案为对应专业的完整培养方案 PDF，")
    lines.append("包含培养目标、毕业要求、课程体系、学分要求、教学计划等详细内容。")
    lines.append("如需查看某专业培养方案的具体内容，可点击对应链接下载 PDF。")
    lines.append("")
    return "\n".join(lines)


def crawl_training_plans() -> list[dict[str, Any]]:
    """采集全部培养方案 PDF。

    仲恺教务部对附件下载启用了验证码拦截，自动脚本无法直接拿到 PDF 二进制。
    本函数会：
      1. 抓取列表页，解析全部专业 PDF 链接；
      2. 尝试逐一下载 PDF，遇到验证码页则跳过该 PDF 的解析；
      3. 无论 PDF 是否拿到，都生成一份完整的培养方案索引文档写入 data/cleaned/jwc/，
         保证 RAG 能回答"有哪些培养方案 / 某专业培养方案链接"类问题。

    返回每份方案的采集结果摘要列表。
    """
    print("[crawl_training_plans] 获取列表页 ...")
    html = _fetch_html(PLAN_LIST_URL)
    save_raw("jwc", "training_plan_list.html", html)

    links = _parse_plan_links(html)
    print(f"[crawl_training_plans] 共发现 {len(links)} 份培养方案 PDF")

    results: list[dict[str, Any]] = []
    succeeded = 0
    captcha_blocked = 0
    # 连续验证码命中计数：连续 3 次命中后认为站点全局拦截，跳过剩余下载
    consecutive_captcha = 0
    skip_remaining = False

    for i, item in enumerate(links, 1):
        name = item["name"]
        major_name = item["major_name"] or name
        stem = _sanitize_filename(major_name) or f"plan_{i}"

        if skip_remaining:
            results.append({**item, "status": "skipped_captcha_global"})
            continue

        print(f"  [{i}/{len(links)}] {name} ...", end=" ", flush=True)

        try:
            pdf_bytes = _fetch_bytes(item["url"])

            if _looks_like_captcha(pdf_bytes):
                # 验证码拦截：记录信息但不写 cleaned 文本
                captcha_blocked += 1
                consecutive_captcha += 1
                print("⚠️ 验证码拦截，跳过 PDF 解析")
                results.append({**item, "status": "captcha_blocked"})
                if consecutive_captcha >= 3:
                    skip_remaining = True
                    print("    连续 3 次验证码拦截，跳过剩余 PDF 下载，仅生成索引")
                time.sleep(settings.crawl_delay)
                continue
            else:
                consecutive_captcha = 0

            # 保存原始 PDF
            raw_pdf_name = f"training_plan_{stem}.pdf"
            save_raw("jwc", raw_pdf_name, pdf_bytes)

            # 解析 PDF 文本
            tmp_path = Path(settings.vector_store_path).parent / "raw" / "jwc" / raw_pdf_name
            parsed = parse_pdf(tmp_path)
            text = parsed.get("full_text", "").strip()

            if not text:
                print("⚠️ PDF 文本为空，跳过")
                captcha_blocked += 1
                results.append({**item, "status": "empty_text"})
                continue

            # 加头部
            header = _build_text_header(item)
            full_text = header + text

            # 保存清洗后文本
            cleaned_name = f"training_plan_{stem}.txt"
            save_cleaned("jwc", cleaned_name, full_text)

            # 保存元数据
            meta = {
                "url": PLAN_LIST_URL,
                "source_url": PLAN_LIST_URL,
                "title": f"{major_name}人才培养方案",
                "department": "教务部",
                "publish_date": PLAN_PUBLISH_DATE,
                "major_code": item.get("major_code", ""),
                "major_name": major_name,
                "page_count": parsed.get("page_count", 0),
                "attachments": [
                    {
                        "name": name,
                        "url": item["url"],
                        "file_type": "pdf",
                    }
                ],
            }
            save_metadata("jwc", cleaned_name.replace(".txt", ".json"), meta)

            succeeded += 1
            print(f"OK ({parsed.get('page_count', 0)} 页)")
            results.append({**item, "status": "ok", "page_count": parsed.get("page_count", 0)})
        except Exception as e:
            captcha_blocked += 1
            print(f"❌ {e}")
            results.append({**item, "status": f"error: {e}"})

        # 礼貌延时
        time.sleep(settings.crawl_delay)

    # 无论 PDF 是否拿到，都生成培养方案总索引文档
    index_text = _build_index_document(links)
    save_cleaned("jwc", "training_plans_index.txt", index_text)
    save_metadata(
        "jwc",
        "training_plans_index.json",
        {
            "url": PLAN_LIST_URL,
            "source_url": PLAN_LIST_URL,
            "title": "2024版本科专业人才培养方案总览",
            "department": "教务部",
            "publish_date": PLAN_PUBLISH_DATE,
            "major_count": len(links),
            "note": "培养方案 PDF 列表索引；PDF 正文受验证码保护需手动下载",
        },
    )

    print(
        f"[crawl_training_plans] 完成：PDF 成功 {succeeded}，"
        f"被验证码拦截/跳过 {captcha_blocked}，"
        f"索引文档已写入 data/cleaned/jwc/training_plans_index.txt"
    )
    return results


def main() -> None:
    """主入口。"""
    print("=" * 60)
    print("ZHKU 培养方案 PDF 采集")
    print("=" * 60)
    crawl_training_plans()
    print("\n可执行 python -m crawler.build_kb 重建知识库")


if __name__ == "__main__":
    main()
