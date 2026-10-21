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

import asyncio
import html
import json
import logging
import math
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections import OrderedDict
from typing import Any

import httpx

from backend.config import settings
from backend.utils.llm_content import extract_text_content
from backend.utils.academic_links import AcademicLinkChecker

logger = logging.getLogger(__name__)

# 在模型不可用时，常见技术查询仍可检索英文文献；未识别的中文不猜译。
_TERMS = {
    "自然语言处理": "natural language processing",
    "计算机视觉": "computer vision",
    "农业监测": "agricultural monitoring",
    "深度学习": "deep learning",
    "机器学习": "machine learning",
    "强化学习": "reinforcement learning",
    "神经网络": "neural networks",
    "目标检测": "object detection",
    "物联网": "internet of things",
    "教育": "education",
    "教学": "teaching",
    "小学": "elementary school",
    "课堂": "classroom",
    "软件工程": "software engineering",
    "软件测试": "software testing",
    "人工智能": "artificial intelligence",
    "图像识别": "image recognition",
    "数据库": "database",
    "计算机网络": "computer networks",
}
_EDUCATION = re.compile(
    r"幼儿|小学|中学|教学|课堂|课程|教育|pedagog|classroom|curriculum|teaching|education",
    re.I,
)
_TECHNICAL = re.compile(
    r"神经网络|卷积|算法|强化学习|机器学习|人工智能|识别|检测|"
    r"neural|network|algorithm|convolution|transformer|machine learning|classification|prediction|detection",
    re.I,
)


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
        self._query_cache = OrderedDict()
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
                timeout=settings.academic_query_timeout_seconds,
                max_retries=0,
            )
        except Exception as e:
            print(f"[AcademicSearchTool] LLM 初始化失败: {e}")

    async def optimize_query(self, question: str) -> tuple[str, str]:
        fast = self._fast_keywords(question)
        if fast:
            return fast
        cache = getattr(self, "_query_cache", None)
        if cache is None:
            self._query_cache = cache = OrderedDict()
        key = " ".join(question.split()).casefold()
        cached = cache.get(key)
        if cached and time.monotonic() - cached[0] < 600:
            cache.move_to_end(key)
            return cached[1]
        keywords = await self._optimize_query(question)
        if keywords[1]:
            cache[key] = (time.monotonic(), keywords)
            cache.move_to_end(key)
            while len(cache) > 128:
                cache.popitem(last=False)
        return keywords

    @classmethod
    def _fast_keywords(cls, question: str) -> tuple[str, str] | None:
        if re.search(r"最新|最近|高引用|高被引|经典|综述|对比|比较|近\s*\d+\s*年", question):
            return None
        query = cls._extract_query(question)
        if re.search(r"[\u4e00-\u9fff]", query):
            translated = cls._to_english_friendly(query)
            return (query, translated) if translated else None
        # 现成英文术语直接检索；较长描述和自然语言请求才交给模型。
        if len(query.split()) <= 8 and not re.search(r"\b(help|find|please|papers?|articles?|latest|recommend)\b", query, re.I):
            return query, query
        return None

    async def _optimize_query(self, question: str) -> tuple[str, str]:
        """用 LLM 将用户自然语言优化为学术搜索关键词（中英文分离）。

        Returns:
            (zh_keywords, en_keywords) — 中英文关键词，Crossref 双语召回，arXiv 英文召回
        """
        if self.llm is None:
            # LLM 不可用时回退到规则提取
            fallback = self._extract_query(question)
            return fallback, self._to_english_friendly(fallback)

        prompt = f"""你是一个学术搜索关键词优化专家。请将用户的自然语言问题转化为最适合在学术论文数据库（Crossref/arXiv）中搜索的关键词。

要求：
1. 提取核心研究领域、技术方法、应用场景等关键词
2. zh_keywords 保留中文专业术语，en_keywords 翻译为英文专业术语，均保留应用场景和学科限定
3. Crossref 会同时使用中英文关键词，arXiv 使用英文关键词
4. 关键词之间用空格分隔，不要加引号
5. 去掉"帮我找""搜索""有没有""关于""的论文"等无关模板词
6. 输出格式为 JSON：{{"zh_keywords": "中文关键词", "en_keywords": "English keywords"}}
7. 没有教育语境时，“深度学习”指人工智能领域的 deep learning；明确提到教学、课堂等时保留教育语境，不能误译为神经网络研究

用户问题：{question}

请输出 JSON："""

        try:
            response = await asyncio.wait_for(self.llm.ainvoke(prompt), timeout=settings.academic_query_timeout_seconds)
            text = extract_text_content(response).strip()
            # 尝试提取 JSON
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            parsed = json.loads(text)
            zh_kw = self._clean_keyword(parsed.get("zh_keywords"))
            en_kw = self._clean_keyword(parsed.get("en_keywords"))

            if not zh_kw:
                zh_kw = self._extract_query(question)
            if not en_kw or re.search(r"[\u4e00-\u9fff]", en_kw):
                en_kw = self._to_english_friendly(zh_kw)

            print(f"[AcademicSearchTool] LLM 关键词优化: '{question}' → zh='{zh_kw}', en='{en_kw}'")
            return zh_kw, en_kw
        except Exception as e:
            print(f"[AcademicSearchTool] LLM 关键词优化失败，回退规则提取: {e}")
            fallback = self._extract_query(question)
            return fallback, self._to_english_friendly(fallback)

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        """兼容工具/普通 JSON 调用方，复用流式流水线的最终结果。"""
        events = self.stream(question, **kwargs)
        try:
            async for event in events:
                if event["type"] == "done":
                    return event["result"]
        finally:
            await events.aclose()
        raise RuntimeError("Academic search did not complete")

    async def stream(self, question: str, **kwargs: Any):
        from backend.utils.academic_pipeline import AcademicSearchPipeline
        if not hasattr(self, "_pipeline"):
            self._pipeline = AcademicSearchPipeline(self)
        events = self._pipeline.stream(question, **kwargs)
        try:
            async for event in events:
                yield event
        finally:
            await events.aclose()

    def _make_link_checker(self) -> AcademicLinkChecker:
        return AcademicLinkChecker(
            concurrency=settings.academic_link_concurrency,
            url_timeout=settings.academic_link_timeout_seconds,
        )

    async def prepare_query(self, question: str, top_k: int, **kwargs: Any) -> dict[str, Any]:
        optimized_kw = kwargs.get("optimized_keywords")
        if optimized_kw and isinstance(optimized_kw, dict):
            zh_query = self._clean_keyword(optimized_kw.get("zh")) or question
            en_query = self._clean_keyword(optimized_kw.get("en"))
        else:
            zh_query, en_query = await self.optimize_query(question)
        return self.query_plan(question, zh_query, en_query, top_k)

    def query_plan(self, question: str, zh_query: str, en_query: str, top_k: int) -> dict[str, Any]:
        en_query = en_query or self._to_english_friendly(zh_query)
        crossref_queries = []
        for query in (en_query, zh_query):
            if query and query.casefold() not in {q.casefold() for q in crossref_queries}:
                crossref_queries.append(query)
        # 裸词有教育学同名含义；在 Crossref 的宽泛元数据检索中明确计算领域。
        if self._normalized(self._extract_query(question)) in {"深度学习", "deeplearning"}:
            context = {"深度学习": "深度学习 神经网络", "deep learning": "deep learning neural networks"}
            crossref_queries = [context.get(q.casefold(), q) for q in crossref_queries]
        limit = max(12, top_k * 3)
        requests = [("Crossref", q) for q in crossref_queries]
        if en_query:
            requests.append(("arXiv", en_query))
        return {"zh": zh_query, "en": en_query, "crossref_queries": crossref_queries,
                "requests": requests, "limit": limit}

    async def _fetch_source(self, source: str, query: str, limit: int) -> dict[str, Any]:
        try:
            search = self._search_crossref if source == "Crossref" else self._search_arxiv
            items = await search(query, limit=limit)
            return {"source": source, "query": query, "status": "success", "items": items}
        except Exception as error:
            logger.warning("Academic source %s failed: %s", source, type(error).__name__)
            if isinstance(error, httpx.TimeoutException):
                message = "请求超时，请稍后重试"
            elif isinstance(error, httpx.HTTPStatusError):
                message = f"服务返回 HTTP {error.response.status_code}，请稍后重试"
            else:
                message = "数据源暂不可用，请稍后重试"
            return {"source": source, "query": query, "status": "error", "message": message, "items": [],
                    "retryable": isinstance(error, (httpx.TimeoutException, httpx.NetworkError)) or
                    (isinstance(error, httpx.HTTPStatusError) and error.response.status_code >= 500)}

    @staticmethod
    def _clean_keyword(value: Any) -> str:
        return " ".join(value.split()) if isinstance(value, str) else ""

    @staticmethod
    def _normalized(value: str) -> str:
        return re.sub(r"[^\w]+", "", unicodedata.normalize("NFKC", value).casefold())

    @staticmethod
    def _title_language(title: str) -> str:
        if re.search(r"[\u4e00-\u9fff]", title):
            return "zh"
        return "en" if re.search(r"[a-z]", title, re.I) else "other"

    @staticmethod
    def _preferred_language(question: str) -> str:
        if re.search(r"(?:英文|英语)(?:的)?(?:论文|文献|原文)|\benglish(?:-language)?\s+(?:papers|articles)", question, re.I):
            return "en"
        return "zh" if re.search(r"[\u4e00-\u9fff]", question) else "en"

    @classmethod
    def _rank_items(cls, batches: list[dict[str, Any]], question: str, zh: str, en: str) -> list[dict[str, Any]]:
        """对中英文等量计分，相关结果按输入语言优先，再融合来源内名次。"""
        computing = bool(re.search(r"深度学习|\bdeep learning\b", question, re.I)) and not _EDUCATION.search(question)
        preferred = cls._preferred_language(question)
        queries = []
        for query in (zh, en):
            terms = set(re.findall(r"[a-z0-9-]{2,}|[\u4e00-\u9fff]+", query.lower()))
            terms -= {"the", "and", "for", "with", "of", "in", "on", "or", "to"}
            if terms:
                queries.append((query, terms))
        documents: list[dict[str, Any]] = []
        doi_index: dict[str, dict[str, Any]] = {}
        title_index: dict[str, dict[str, Any]] = {}
        for batch in batches:
            for rank, item in enumerate(batch["items"], 1):
                title = cls._normalized(item.get("title", ""))
                if not title:
                    continue
                text = f"{item.get('title', '')} {item.get('snippet', '')} {item.get('venue', '')}"
                if computing and _EDUCATION.search(text) and not _TECHNICAL.search(text):
                    continue
                doi = re.sub(r"^https?://(?:dx\.)?doi.org/", "", item.get("doi", "").strip().lower())
                doc = doi_index.get(doi) if doi else None
                doc = doc or title_index.get(title)
                if doc is None:
                    doc = {"item": dict(item), "ranks": {}}
                    documents.append(doc)
                else:
                    # 同一 DOI 的双语元数据优先展示用户语言的真实标题。
                    if cls._title_language(item["title"]) == preferred and cls._title_language(doc["item"]["title"]) != preferred:
                        doc["item"]["title"] = item["title"]
                    # 合并预印本与正式版本的元数据，保留更完整的摘要与 DOI。
                    for key in ("doi", "authors", "year", "url"):
                        if not doc["item"].get(key) and item.get(key):
                            doc["item"][key] = item[key]
                    if len(item.get("snippet", "")) > len(doc["item"].get("snippet", "")):
                        doc["item"]["snippet"] = item["snippet"]
                    doc["item"]["cited"] = max(doc["item"].get("cited", 0), item.get("cited", 0))
                if doi:
                    doi_index[doi] = doc
                title_index[title] = doc
                source = batch["source"]
                doc["ranks"][source] = min(rank, doc["ranks"].get(source, rank))

        def relevance(doc: dict[str, Any]) -> float:
            item = doc["item"]
            title = item.get("title", "").lower()
            abstract = item.get("snippet", "").lower()
            # 各语种分别归一化，取最佳匹配，避免一个中文词被多个英文词稀释。
            return max((
                sum(4 * (t in title) + (t in abstract) for t in terms) / len(terms)
                + (2 if cls._normalized(query) in cls._normalized(title) else 0)
                for query, terms in queries
            ), default=0)

        def score(doc: dict[str, Any]) -> tuple[bool, float]:
            item = doc["item"]
            title = item.get("title", "").lower()
            abstract = item.get("snippet", "").lower()
            match = relevance(doc)
            technical = 0.5 if computing and _TECHNICAL.search(f"{title} {abstract}") else 0
            citations = 0.05 * math.log1p(min(max(item.get("cited", 0), 0), 10000))
            # 同一来源的中英文查询不重复加权，避免双语召回挤占另一来源。
            fusion = sum(1 / (20 + rank) for rank in doc["ranks"].values())
            language_match = cls._title_language(title) == preferred and match > 0
            return language_match, match + technical + citations + fusion

        documents.sort(key=score, reverse=True)
        return [doc["item"] for doc in documents]

    async def _search_crossref(
        self, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """调用 Crossref API 搜索论文。"""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.crossref.org/works",
                params={
                    "query.bibliographic": query,
                    "rows": limit,
                    "sort": "relevance",
                    "filter": "type:journal-article,type:proceedings-article,type:posted-content",
                    "select": "title,author,published-print,published-online,published,DOI,is-referenced-by-count,URL,type,abstract,container-title,resource",
                },
            )
            resp.raise_for_status()

            data = resp.json()
            message = data.get("message") if isinstance(data, dict) else None
            if not isinstance(message, dict) or not isinstance(message.get("items"), list):
                raise ValueError("Invalid Crossref response")
            items = message["items"]
            results: list[dict[str, Any]] = []

            for item in items:
                title = self._strip_markup(item.get("title", [""])[0]) if item.get("title") else ""
                if not title:
                    continue
                if re.search(r"\b(?:program|organi[sz]ing) committee\b|message from.*chairs|table of contents|front matter", title, re.I):
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
                published = item.get("published", {}).get("date-parts", [[]])
                year = ""
                for parts in [pub_print, pub_online, published]:
                    if parts and parts[0]:
                        year = str(parts[0][0])
                        break

                doi = item.get("DOI", "")
                cited = item.get("is-referenced-by-count", 0)
                # 直接使用登记的出版社落地页，避免每篇都先经过 DOI 中转。
                resource = item.get("resource") or {}
                url = (resource.get("primary") or {}).get("URL") or item.get("URL", "")

                results.append({
                    "title": title,
                    "authors": authors,
                    "year": year,
                    "doi": doi,
                    "cited": cited,
                    "url": url or (f"https://doi.org/{doi}" if doi else ""),
                    "source": "Crossref",
                    "department": "Crossref API",
                    "venue": " ".join(item.get("container-title", []) or []),
                    "publish_date": year,
                    "snippet": self._strip_markup(item.get("abstract", ""))[:1200],
                })

            return results

    async def _search_arxiv(
        self, query: str, limit: int = 3
    ) -> list[dict[str, Any]]:
        """调用 arXiv API 搜索预印本论文。"""
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                "https://export.arxiv.org/api/query",
                params={
                    "search_query": self._build_arxiv_query(query),
                    "max_results": limit,
                    "sortBy": "relevance",
                },
            )
            resp.raise_for_status()

            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
            if root.tag != "{http://www.w3.org/2005/Atom}feed":
                raise ValueError("Invalid arXiv feed")
            entries = root.findall("atom:entry", ns)
            results: list[dict[str, Any]] = []

            for entry in entries:
                title_el = entry.find("atom:title", ns)
                title = " ".join((title_el.text or "").split()) if title_el is not None else ""
                if not title:
                    continue

                published_el = entry.find("atom:published", ns)
                published = (published_el.text or "")[:10] if published_el is not None else ""

                link_el = entry.find("atom:id", ns)
                link = (link_el.text or "") if link_el is not None else ""
                if link.startswith("http://arxiv.org/api/errors") or link.startswith("https://arxiv.org/api/errors"):
                    raise ValueError("arXiv query error")

                summary_el = entry.find("atom:summary", ns)
                abstract = " ".join((summary_el.text or "").split())[:1200] if summary_el is not None else ""

                # 提取作者
                author_els = entry.findall("atom:author/atom:name", ns)
                authors = ", ".join(a.text.strip() for a in author_els[:5] if a.text)
                if len(author_els) > 5:
                    authors += " et al."

                results.append({
                    "title": title,
                    "authors": authors,
                    "year": published[:4] if published else "",
                    "doi": entry.findtext("arxiv:doi", default="", namespaces=ns).strip(),
                    "cited": 0,
                    "url": link,
                    "source": "arXiv",
                    "department": "arXiv API",
                    "publish_date": published,
                    "snippet": abstract,
                })

            return results

    @staticmethod
    def _strip_markup(value: str) -> str:
        return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", value or "")).split())

    @staticmethod
    def _build_arxiv_query(query: str) -> str:
        # 常见复合术语按短语检索，其余词显式 AND，避免把空格当作查询语法。
        phrases = (
            r"natural language processing|reinforcement learning|deep learning|"
            r"machine learning|computer vision|neural networks?|object detection|internet of things"
        )
        terms = re.findall(rf"\b(?:{phrases})\b|[a-z0-9][a-z0-9-]*", query.lower())
        terms = [t for t in terms if t not in {"and", "or", "the", "of", "for", "in", "with"}]
        return " AND ".join(f'all:"{term}"' for term in terms)

    @staticmethod
    def _extract_query(question: str) -> str:
        """从问题中提取搜索关键词。"""
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
        """仅翻译可识别的常见术语；其余中文由 LLM 翻译或显式跳过 arXiv。"""
        for zh, en in _TERMS.items():
            query = query.replace(zh, f" {en} ")
        if re.search(r"[\u4e00-\u9fff]", query):
            return ""
        return " ".join(query.split())
