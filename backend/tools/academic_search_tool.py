"""学术搜索工具。

调用 Crossref API 和 arXiv API 搜索学术论文，无需 API Key。
Crossref：覆盖全学科 1.5 亿+论文，支持中文查询，返回 JSON。
arXiv：覆盖 CS/物理/数学预印本，返回 XML。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import httpx


class AcademicSearchTool:
    """学术搜索工具。

    第三方 API 工具，调用 Crossref + arXiv 搜索学术论文。
    完全免费，无需 API Key。
    """

    name = "academic_search"
    description = "搜索学术论文，支持按关键词查找论文标题、作者、DOI、引用数等信息"

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        """搜索学术论文。

        同时查询 Crossref 和 arXiv，合并去重后返回。
        """
        query = self._extract_query(question)
        top_k = kwargs.get("top_k", 5)

        items: list[dict[str, Any]] = []

        # Crossref 搜索
        cr_results = await self._search_crossref(query, limit=top_k)
        items.extend(cr_results)

        # arXiv 搜索（仅英文关键词效果好）
        arxiv_query = self._to_english_friendly(query)
        if arxiv_query:
            arxiv_results = await self._search_arxiv(arxiv_query, limit=min(top_k, 3))
            items.extend(arxiv_results)

        # 去重（按标题相似度）
        seen_titles: set[str] = set()
        unique_items: list[dict[str, Any]] = []
        for item in items:
            key = item.get("title", "").lower().strip()[:60]
            if key not in seen_titles:
                seen_titles.add(key)
                unique_items.append(item)

        return {
            "tool": self.name,
            "items": unique_items[:top_k],
            "total": len(unique_items),
        }

    async def _search_crossref(
        self, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """调用 Crossref API 搜索论文。"""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.crossref.org/works",
                    params={
                        "query": query,
                        "rows": limit,
                        "sort": "relevance",
                        "select": "title,author,published-print,published-online,DOI,is-referenced-by-count,URL,type",
                    },
                )
                if resp.status_code != 200:
                    return []

                data = resp.json()
                items = data.get("message", {}).get("items", [])
                results: list[dict[str, Any]] = []

                for item in items:
                    title = item.get("title", [""])[0] if item.get("title") else ""
                    if not title:
                        continue

                    # 提取作者
                    authors_list = item.get("author", []) or []
                    authors = ", ".join(
                        f"{a.get('given', '')} {a.get('family', '')}".strip()
                        for a in authors_list[:5]
                    )
                    if len(authors_list) > 5:
                        authors += " et al."

                    # 提取年份
                    pub_print = item.get("published-print", {}).get("date-parts", [[]])
                    pub_online = item.get("published-online", {}).get("date-parts", [[]])
                    year = ""
                    for parts in [pub_print, pub_online]:
                        if parts and parts[0]:
                            year = str(parts[0][0])
                            break

                    doi = item.get("DOI", "")
                    cited = item.get("is-referenced-by-count", 0)
                    url = item.get("URL", "")

                    results.append({
                        "title": title,
                        "authors": authors,
                        "year": year,
                        "doi": doi,
                        "cited": cited,
                        "url": url or f"https://doi.org/{doi}" if doi else "",
                        "source": "Crossref",
                        "department": "Crossref API",
                        "publish_date": year,
                        "snippet": f"引用数: {cited}, DOI: {doi}",
                    })

                return results

        except httpx.HTTPError:
            return []

    async def _search_arxiv(
        self, query: str, limit: int = 3
    ) -> list[dict[str, Any]]:
        """调用 arXiv API 搜索预印本论文。"""
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(
                    "https://export.arxiv.org/api/query",
                    params={
                        "search_query": f"all:{query}",
                        "max_results": limit,
                        "sortBy": "relevance",
                    },
                )
                if resp.status_code != 200:
                    return []

                root = ET.fromstring(resp.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                entries = root.findall("atom:entry", ns)
                results: list[dict[str, Any]] = []

                for entry in entries:
                    title_el = entry.find("atom:title", ns)
                    title = title_el.text.strip().replace("\n", " ") if title_el is not None else ""
                    if not title:
                        continue

                    published_el = entry.find("atom:published", ns)
                    published = published_el.text[:10] if published_el is not None else ""

                    link_el = entry.find("atom:id", ns)
                    link = link_el.text if link_el is not None else ""

                    summary_el = entry.find("atom:summary", ns)
                    abstract = summary_el.text.strip()[:300] if summary_el is not None else ""

                    # 提取作者
                    author_els = entry.findall("atom:author/atom:name", ns)
                    authors = ", ".join(a.text.strip() for a in author_els[:5] if a.text)
                    if len(author_els) > 5:
                        authors += " et al."

                    results.append({
                        "title": title,
                        "authors": authors,
                        "year": published[:4] if published else "",
                        "doi": "",
                        "cited": 0,
                        "url": link,
                        "source": "arXiv",
                        "department": "arXiv API",
                        "publish_date": published,
                        "snippet": abstract,
                    })

                return results

        except (httpx.HTTPError, ET.ParseError):
            return []

    @staticmethod
    def _extract_query(question: str) -> str:
        """从问题中提取搜索关键词。"""
        import re
        # 去掉常见问句模板
        q = question
        patterns = [
            r"帮我找(一下|一些)?",
            r"搜索(一下)?",
            r"查(一查|一下)?",
            r"有没有",
            r"关于",
            r"方向",
            r"的论文.*$",
            r"的文献.*$",
            r"论文.*$",
            r"文献.*$",
            r"相关.*$",
            r"有哪些.*$",
        ]
        for p in patterns:
            q = re.sub(p, "", q)
        return q.strip() or question

    @staticmethod
    def _to_english_friendly(query: str) -> str:
        """将查询转为 arXiv 友好的格式（arXiv 英文搜索效果好）。

        中文查询直接跳过 arXiv，避免返回无关结果。
        """
        # 如果查询主要是中文，跳过 arXiv
        import re
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", query)
        if len(chinese_chars) > len(query) * 0.3:
            return ""
        return query
