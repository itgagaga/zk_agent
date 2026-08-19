"""本科专业与培养方案查询工具。"""
from __future__ import annotations

from typing import Any

from backend.tools.base import BaseTool


class MajorTool(BaseTool):
    """专业查询工具。

    数据源：metadata JSON 中的 download_items / summary 字段
    （由数据采集阶段从教务部专业目录和培养方案页面整理生成）。
    """

    name = "major_search"
    description = "根据专业名、专业代码、学院查询本科专业信息及培养方案入口"

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        """查询专业信息。

        从 metadata JSON 中查找专业目录和培养方案相关资料。
        """
        top_k = kwargs.get("top_k", 10)
        keywords = self._extract_keywords(question)

        items: list[dict[str, Any]] = []
        for meta in self._load_all_metadata():
            tags = meta.get("tags", [])
            # 查和专业/学院/机构/培养方案相关的 metadata
            relevant_tags = [
                "本科专业目录", "培养方案", "通识选修课",
                "机构设置", "二级学院", "教学机构", "部门",
            ]
            if not any(t in tags for t in relevant_tags):
                continue

            match_text = " ".join(
                str(meta.get(k, ""))
                for k in ("title", "summary", "department")
            )
            match_text += " " + self._metadata_search_text(meta)
            if not keywords or self._keyword_match(match_text, keywords):
                # 把 download_items 中的专业目录 / 培养方案入口也带上
                for dl in meta.get("download_items", []) or []:
                    items.append(
                        {
                            "title": dl.get("name", meta.get("title", "")),
                            "file_url": dl.get("url", ""),
                            "source_page_url": meta.get("source_url", ""),
                            "publish_date": dl.get("date", ""),
                            "department": meta.get("department", ""),
                            "category": meta.get("category", ""),
                            "subcategory": meta.get("subcategory", ""),
                        }
                    )
                if not meta.get("download_items"):
                    items.append(
                        {
                            "title": meta.get("title", ""),
                            "source_page_url": meta.get("source_url", ""),
                            "publish_date": meta.get("publish_date", ""),
                            "department": meta.get("department", ""),
                            "summary": meta.get("summary", ""),
                        }
                    )

        ranked = self._rank_items(
            question,
            items,
            title_fields=("title",),
            text_fields=("department", "category", "subcategory", "summary"),
        )
        return {"tool": self.name, "items": ranked[:top_k], "total": len(ranked)}
