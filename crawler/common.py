"""采集通用工具。

提供统一的 HTTP 请求、HTML 解析、附件识别、元数据保存能力。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from backend.config import settings
from crawler.classification import classify_metadata

# 项目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_CLEANED_DIR = PROJECT_ROOT / "data" / "cleaned"
DATA_METADATA_DIR = PROJECT_ROOT / "data" / "metadata"


def fetch(url: str, *, encoding: str = "utf-8", referer: str = "") -> str:
    """发起 HTTP 请求，返回 HTML 文本。"""
    headers = {"User-Agent": settings.crawl_user_agent}
    if referer:
        headers["Referer"] = referer
    resp = requests.get(
        url, headers=headers, timeout=settings.crawl_timeout
    )
    resp.raise_for_status()
    if encoding:
        resp.encoding = encoding
    # 礼貌延时
    time.sleep(settings.crawl_delay)
    return resp.text


def parse_html(html: str) -> BeautifulSoup:
    """解析 HTML。"""
    return BeautifulSoup(html, "lxml")


def extract_main_text(soup: BeautifulSoup) -> str:
    """提取网页正文文本。

    简单实现：去除 script/style/nav/footer/header，取正文区域。
    """
    for tag in soup(["script", "style", "nav", "footer", "header", "iframe"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def extract_title(soup: BeautifulSoup) -> str:
    """提取页面标题。"""
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return ""


def extract_publish_date(soup: BeautifulSoup) -> str | None:
    """提取发布时间。

    仲恺官网常见格式：作者：xxx  发布时间：2026-04-28
    """
    text = soup.get_text(separator="\n", strip=True)
    for line in text.splitlines():
        if "发布时间" in line:
            # 简单截取
            return line.strip()
    return None


def extract_attachments(soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
    """提取附件链接。"""
    attachments: list[dict[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        name = a.get_text(strip=True)
        if not name:
            continue
        lower = href.lower()
        if lower.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar")):
            attachments.append(
                {
                    "name": name,
                    "url": _absolute_url(href, base_url),
                    "file_type": Path(href).suffix.lstrip(".").lower(),
                }
            )
    return attachments


def _absolute_url(href: str, base_url: str) -> str:
    """将相对 URL 转绝对 URL。"""
    from urllib.parse import urljoin

    return urljoin(base_url, href)


def save_raw(subdir: str, filename: str, content: str | bytes) -> Path:
    """保存原始内容到 data/raw/<subdir>/<filename>。"""
    target_dir = DATA_RAW_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    if isinstance(content, bytes):
        target.write_bytes(content)
    else:
        target.write_text(content, encoding="utf-8")
    return target


def save_cleaned(subdir: str, filename: str, text: str) -> Path:
    """保存清洗后文本到 data/cleaned/<subdir>/<filename>。"""
    target_dir = DATA_CLEANED_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    target.write_text(text, encoding="utf-8")
    return target


def save_metadata(subdir: str, filename: str, data: dict[str, Any]) -> Path:
    """保存元数据 JSON 到 data/metadata/<subdir>/<filename>。"""
    import json

    data = classify_metadata(data, subdir, filename)
    target_dir = DATA_METADATA_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target
