"""部门联系方式查询工具。"""
from __future__ import annotations

from typing import Any

from backend.tools.base import BaseTool


class ContactTool(BaseTool):
    """联系方式查询工具。

    数据源：metadata JSON 中的 contacts 字段
    （由数据采集阶段从后勤、网络、校医院等联系方式页面整理生成）。
    """

    name = "contact_search"
    description = "查询后勤、网络、校医院、招生、研究生等公开电话与办公地点"

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        """查询联系方式。

        从 metadata JSON 的 contacts 字段中按关键词匹配。
        """
        top_k = kwargs.get("top_k", 15)
        keywords = self._extract_keywords(question)

        items: list[dict[str, Any]] = []
        for meta in self._load_all_metadata():
            source_url = (
                meta.get("source_url")
                or (meta.get("source_url_list") or [None])[0]
                or meta.get("url")
                or ""
            )
            for contact in meta.get("contacts", []) or []:
                # 把所有字段拼成一个文本用于匹配
                match_text = " ".join(str(v) for v in contact.values())
                match_text += " " + self._metadata_search_text(meta)
                if not keywords or self._keyword_match(match_text, keywords):
                    # 校医院等条目用 location，学生工作部等用 service/department
                    title = (
                        contact.get("department")
                        or contact.get("service")
                        or contact.get("location")
                        or contact.get("name")
                        or ""
                    )
                    address = contact.get("address") or contact.get("location") or ""
                    phone = contact.get("phone", "")
                    snippet_parts = [p for p in (address, phone and f"电话 {phone}") if p]
                    items.append(
                        {
                            "title": title,
                            "phone": phone,
                            "address": address,
                            "location": contact.get("location", ""),
                            "department": meta.get("department", ""),
                            "category": meta.get("category", ""),
                            "subcategory": meta.get("subcategory", ""),
                            "source_page_url": source_url,
                            "snippet": " · ".join(snippet_parts),
                        }
                    )

        return {"tool": self.name, "items": items[:top_k], "total": len(items)}
