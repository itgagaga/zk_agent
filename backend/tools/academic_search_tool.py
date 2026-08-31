"""学术搜索工具。

调用 Crossref API 和 arXiv API 搜索学术论文，无需 API Key。
Crossref：覆盖全学科 1.5 亿+论文，支持中文查询，返回 JSON。
arXiv：覆盖 CS/物理/数学预印本，返回 XML。

LLM 参与流程：
1. 用户自然语言 → LLM 优化为学术搜索关键词
2. 优化后的关键词 → Crossref / arXiv API 搜索
3. 搜索结果 → LLM 整合分析生成回答
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from backend.config import settings
from backend.utils.llm_content import extract_text_content


class AcademicSearchTool:
    """学术搜索工具。

    LLM + 第三方 API 协作：
    - LLM（DeepSeek）优化用户查询为学术搜索关键词
    - Crossref + arXiv API 执行实际论文检索
    - LLM 整合分析搜索结果
    """

    name = "academic_search"
    description = "搜索学术论文，支持按关键词查找论文标题、作者、DOI、引用数等信息"

    def __init__(self) -> None:
        self.llm: Any = None
        self._init_llm()

    def _init_llm(self) -> None:
        """初始化 DeepSeek LLM 客户端用于关键词优化。"""
        if not settings.deepseek_api_key:
            return
        try:
            from langchain_deepseek import ChatDeepSeek

            self.llm = ChatDeepSeek(
                model=settings.deepseek_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=0.1,
                max_tokens=300,
            )
        except Exception as e:
            print(f"[AcademicSearchTool] LLM 初始化失败: {e}")

    async def optimize_query(self, question: str) -> tuple[str, str]:
        """用 LLM 将用户自然语言优化为学术搜索关键词（中英文分离）。

        Returns:
            (zh_keywords, en_keywords) — 中文关键词（Crossref 用）、英文关键词（arXiv 用）
        """
        if self.llm is None:
            # LLM 不可用时回退到规则提取
            fallback = self._extract_query(question)
            return fallback, self._to_english_friendly(fallback)

        prompt = f"""你是一个学术搜索关键词优化专家。请将用户的自然语言问题转化为最适合在学术论文数据库（Crossref/arXiv）中搜索的关键词。

要求：
1. 提取核心研究领域、技术方法、应用场景等关键词
2. zh_keywords 用于 Crossref（支持中文），保留中文专业术语
3. en_keywords 用于 arXiv（仅英文有效），翻译为英文专业术语
4. 关键词之间用空格分隔，不要加引号
5. 去掉"帮我找""搜索""有没有""关于""的论文"等无关模板词
6. 输出格式为 JSON：{{"zh_keywords": "中文关键词", "en_keywords": "English keywords"}}

用户问题：{question}

请输出 JSON："""

        try:
            response = await self.llm.ainvoke(prompt)
            text = extract_text_content(response).strip()
            # 尝试提取 JSON
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            parsed = json.loads(text)
            zh_kw = parsed.get("zh_keywords", "").strip()
            en_kw = parsed.get("en_keywords", "").strip()

            if not zh_kw:
                zh_kw = self._extract_query(question)
            if not en_kw:
                en_kw = self._to_english_friendly(zh_kw)

            print(f"[AcademicSearchTool] LLM 关键词优化: '{question}' → zh='{zh_kw}', en='{en_kw}'")
            return zh_kw, en_kw
        except (json.JSONDecodeError, Exception) as e:
            print(f"[AcademicSearchTool] LLM 关键词优化失败，回退规则提取: {e}")
            fallback = self._extract_query(question)
            return fallback, self._to_english_friendly(fallback)

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        """搜索学术论文。

        LLM Agent 工具调用流程：
        1. LLM 优化用户问题为学术搜索关键词（中英文分离）
        2. 中文关键词 → Crossref API 搜索
        3. 英文关键词 → arXiv API 搜索
        4. 合并去重后返回
        """
        top_k = kwargs.get("top_k", 5)

        # 优先使用调用方提供的优化关键词
        optimized_kw = kwargs.get("optimized_keywords")
        if optimized_kw and isinstance(optimized_kw, dict):
            zh_query = optimized_kw.get("zh", question)
            en_query = optimized_kw.get("en", "")
        else:
            # LLM 优化关键词（中英文分离）
            zh_query, en_query = await self.optimize_query(question)

        items: list[dict[str, Any]] = []

        # Crossref 搜索（用中文或组合关键词）
        cr_query = zh_query
        cr_results = await self._search_crossref(cr_query, limit=top_k)
        items.extend(cr_results)

        # arXiv 搜索（优先用英文关键词，效果更好）
        arxiv_query = en_query if en_query else self._to_english_friendly(zh_query)
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
            "query_used": {"zh": zh_query, "en": en_query or arxiv_query},
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
