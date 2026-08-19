"""资料下载查询工具。"""
from __future__ import annotations

from typing import Any

from backend.tools.base import BaseTool


class DownloadTool(BaseTool):
    """资料下载查询工具。

    数据源：metadata JSON 中的 download_items 字段
    （由数据采集阶段从教务部、研究生处下载栏目整理生成）。
    """

    name = "download_search"
    description = "根据关键词查询教务申请表、流程图、培养方案、研究生表格等下载资料"

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        """查询下载资料。

        从 metadata JSON 的 download_items 字段中按关键词匹配。
        """
        top_k = int(kwargs.get("top_k", 10))
        category = kwargs.get("category") or None
        audience = kwargs.get("audience") or None
        candidates: list[dict[str, Any]] = []
        for meta in self._load_all_metadata():
            for item in meta.get("download_items", []) or []:
                if not isinstance(item, dict):
                    continue
                item_url = item.get("url") or item.get("file_url") or ""
                title = item.get("name") or item.get("title") or item.get("filename") or ""
                if not title:
                    continue
                normalized = {
                    "title": title,
                    "file_url": item_url,
                    "source_page_url": (
                        item.get("source_page_url")
                        or meta.get("source_page_url")
                        or meta.get("source_url")
                        or ""
                    ),
                    "publish_date": (
                        item.get("date")
                        or item.get("publish_date")
                        or meta.get("publish_date")
                        or ""
                    ),
                    "department": item.get("department") or meta.get("department") or "",
                    "category": item.get("category") or meta.get("category") or "",
                    "subcategory": item.get("subcategory") or meta.get("subcategory") or "",
                    "audience": item.get("audience") or meta.get("audience") or "",
                    "document_type": item.get("document_type") or meta.get("document_type") or "",
                    "file_type": item.get("file_type") or "",
                }
                candidates.append(normalized)

        facets = {
            "categories": sorted(
                {item["category"] for item in candidates if item["category"]}
            ),
            "audiences": sorted(
                {item["audience"] for item in candidates if item["audience"]}
            ),
        }
        filtered = [
            item
            for item in candidates
            if (category is None or item["category"] == category)
            and (audience is None or item["audience"] == audience)
        ]

        seen: set[tuple[str, str]] = set()
        unique: list[dict[str, Any]] = []
        for item in filtered:
            key = (item["title"], item["file_url"] or item["source_page_url"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)

        ranked = self._rank_items(
            question,
            unique,
            title_fields=("title",),
            text_fields=("department", "category", "subcategory", "audience", "document_type"),
        )
        return {
            "tool": self.name,
            "items": ranked[:top_k],
            "total": len(ranked),
            "facets": facets,
        }
