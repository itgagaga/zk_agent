"""新闻公告检索工具。"""
from __future__ import annotations

from typing import Any

from backend.tools.base import BaseTool


class NewsTool(BaseTool):
    """新闻公告检索工具。

    数据源：SQLite news_article 表 + FTS5 全文索引。
    """

    name = "news_search"
    description = "按关键词和栏目检索学校要闻、通知公告、校园快讯等动态"

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        """查询新闻公告。

        kwargs 可包含：
            keyword: 关键词
            category: 栏目（学校要闻/通知公告/校园快讯/媒体仲恺/学术科研）
            top_k: 返回条数上限
        """
        # TODO: 接入 SQLite FTS5 查询
        return {"tool": self.name, "items": [], "total": 0}
