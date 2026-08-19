"""服务入口查询工具。"""
from __future__ import annotations

from typing import Any

from backend.tools.base import BaseTool


class ServiceLinkTool(BaseTool):
    """服务入口查询工具。

    数据源：metadata JSON 中的 service_links 字段
    （由数据采集阶段从现代教育技术中心等服务页面整理生成）。
    """

    name = "service_link_search"
    description = "查询 OA、邮箱、VPN、教务、就业、研究生、资产、人事等系统入口"

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        """查询服务入口。

        从 metadata JSON 的 service_links 字段中按关键词匹配。
        """
        top_k = kwargs.get("top_k", 15)
        keywords = self._extract_keywords(question)

        items: list[dict[str, Any]] = []
        for meta in self._load_all_metadata():
            service_links = meta.get("service_links", {})
            if not isinstance(service_links, dict):
                continue
            for link_name, link_url in service_links.items():
                match_text = f"{link_name} {self._metadata_search_text(meta)}"
                if not keywords or self._keyword_match(match_text, keywords):
                    items.append(
                        {
                            "title": link_name,
                            "url": link_url,
                            "department": meta.get("department", ""),
                            "category": meta.get("category", ""),
                            "subcategory": meta.get("subcategory", ""),
                            "source_page_url": meta.get("source_url", ""),
                        }
                    )

        return {"tool": self.name, "items": items[:top_k], "total": len(items)}
