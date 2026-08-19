"""工具基类。

所有结构化工具继承此类，实现 run 方法。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR
from crawler.resource_download import normalize_download_items


class BaseTool:
    """工具基类。"""

    name: str = "base_tool"
    description: str = ""

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        """执行工具查询，返回标准化字典。

        返回格式：
            {
                "tool": "工具名",
                "items": [...],   # 命中条目列表
                "total": int,
            }
        """
        raise NotImplementedError

    @staticmethod
    def _load_all_metadata() -> list[dict[str, Any]]:
        """加载 data/metadata/ 下所有 JSON 文件。"""
        metadata_dir = DATA_DIR / "metadata"
        if not metadata_dir.exists():
            return []
        results: list[dict[str, Any]] = []
        for json_file in sorted(metadata_dir.rglob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                download_items = normalize_download_items(data)
                if download_items:
                    data = {**data, "download_items": download_items}
                results.append(data)
            except Exception:
                continue
        return results

    @staticmethod
    def _keyword_match(text: str, keywords: list[str]) -> bool:
        """检查 text 中是否包含任意关键词。"""
        text_lower = text.lower()
        return any(k.lower() in text_lower for k in keywords if k)

    @staticmethod
    def _metadata_search_text(meta: dict[str, Any]) -> str:
        """把功能分类字段纳入结构化工具的关键词匹配。"""
        values = [
            meta.get("title", ""),
            meta.get("summary", ""),
            meta.get("department", ""),
            meta.get("category", ""),
            meta.get("subcategory", ""),
            meta.get("audience", ""),
            meta.get("document_type", ""),
            meta.get("tags", ""),
        ]
        return " ".join(",".join(value) if isinstance(value, list) else str(value) for value in values)

    @staticmethod
    def _extract_keywords(question: str) -> list[str]:
        """从中文问题中提取关键词（2-gram 滑动窗口）。

        中文没有空格分词，用 2 字连续子串作为关键词。
        过滤掉包含标点符号的 2-gram。
        """
        import re

        # 去掉标点和空格
        clean = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", question)
        if len(clean) < 2:
            return [clean] if clean else []
        # 取所有 2-gram
        return [clean[i : i + 2] for i in range(len(clean) - 1)]

    @staticmethod
    def _query_terms(question: str) -> list[str]:
        """提取用于结构化候选排序的短语，过滤问句模板词。"""
        clean = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", question).lower()
        stop = {
            "哪里", "在哪", "怎么", "如何", "查询", "查找", "有没有", "帮我",
            "下载", "一下", "请问", "什么", "哪个", "哪些", "可以", "吗", "呢",
        }
        terms: set[str] = set()
        for size in (4, 3, 2):
            for index in range(len(clean) - size + 1):
                term = clean[index : index + size]
                if term not in stop:
                    terms.add(term)
        return sorted(terms, key=lambda value: (-len(value), value))

    @classmethod
    def _rank_items(
        cls,
        question: str,
        items: list[dict[str, Any]],
        *,
        title_fields: tuple[str, ...] = ("title", "name"),
        text_fields: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        """按标题精确度和字段匹配度稳定排序结构化候选。"""
        terms = cls._query_terms(question)
        normalized_question = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", question).lower()
        ranked: list[tuple[float, int, dict[str, Any]]] = []
        for index, item in enumerate(items):
            title = " ".join(str(item.get(field, "")) for field in title_fields).lower()
            body = " ".join(
                str(item.get(field, "")) for field in (*title_fields, *text_fields)
            ).lower()
            score = 0.0
            if normalized_question and normalized_question in title:
                score += 20.0
            for term in terms:
                if term in title:
                    score += 2.0 + len(term)
                elif term in body:
                    score += 0.5 + len(term) * 0.25
            if score > 0:
                item = {**item, "match_score": round(score, 4)}
            ranked.append((score, index, item))
        ranked.sort(key=lambda row: (-row[0], row[1], str(row[2].get("title", ""))))
        if not normalized_question and not terms:
            return [item for _, _, item in ranked]
        return [item for score, _, item in ranked if score > 0]
