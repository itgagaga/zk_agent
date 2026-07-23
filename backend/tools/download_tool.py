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
        top_k = kwargs.get("top_k", 10)
        keywords = self._extract_keywords(question)

        items: list[dict[str, Any]] = []
        for meta in self._load_all_metadata():
            for item in meta.get("download_items", []) or []:
                name = item.get("name", "")
                if not name:
                    continue
                # 如果没有关键词，返回全部；否则按关键词匹配
                if not keywords or self._keyword_match(name, keywords):
                    items.append(
                        {
                            "title": name,
                            "file_url": item.get("url", ""),
                            "source_page_url": meta.get("source_url", ""),
                            "publish_date": item.get("date", ""),
                            "department": meta.get("department", ""),
                        }
                    )

        # 去重
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for item in items:
            key = item["title"]
            if key not in seen:
                seen.add(key)
                unique.append(item)

        return {"tool": self.name, "items": unique[:top_k], "total": len(unique)}
