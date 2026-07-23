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
            for contact in meta.get("contacts", []) or []:
                # 把所有字段拼成一个文本用于匹配
                match_text = " ".join(str(v) for v in contact.values())
                if not keywords or self._keyword_match(match_text, keywords):
                    items.append(
                        {
                            "title": contact.get("department") or contact.get("service", ""),
                            "phone": contact.get("phone", ""),
                            "address": contact.get("address", ""),
                            "location": contact.get("location", ""),
                            "department": meta.get("department", ""),
                            "source_page_url": meta.get("source_url", ""),
                        }
                    )

        return {"tool": self.name, "items": items[:top_k], "total": len(items)}
