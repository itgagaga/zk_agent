"""工具基类。

所有结构化工具继承此类，实现 run 方法。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR


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
        for json_file in sorted(metadata_dir.glob("*.json")):
            try:
                results.append(json.loads(json_file.read_text(encoding="utf-8")))
            except Exception:
                continue
        return results

    @staticmethod
    def _keyword_match(text: str, keywords: list[str]) -> bool:
        """检查 text 中是否包含任意关键词。"""
        text_lower = text.lower()
        return any(k.lower() in text_lower for k in keywords if k)

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

