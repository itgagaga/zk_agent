"""兜底处理模块。

当 RAG 无可靠依据、工具无结果、或问题超出范围时，
明确告知用户"未找到可靠依据"，不编造答案。
"""
from __future__ import annotations

from typing import Any

from backend.config import settings

# 兜底回答文案
FALLBACK_MESSAGE = (
    "未在当前已采集的仲恺农业工程学院公开资料中找到可靠依据，"
    "建议访问对应部门官网或联系学校相关部门确认。"
)


class FallbackHandler:
    """兜底处理器。"""

    def __init__(self) -> None:
        self.enabled = settings.enable_fallback

    def no_evidence(self, question: str, message: str | None = None) -> dict[str, Any]:
        """无依据兜底。"""
        return {
            "answer": message or FALLBACK_MESSAGE,
            "confidence": "low",
            "sources": [],
            "attachments": [],
            "tools_used": [],
            "fallback": True,
            "session_id": None,
        }

    def low_confidence(self, question: str, answer: str) -> dict[str, Any]:
        """低置信度兜底，附加提示。"""
        return {
            "answer": answer + "\n\n注：以上内容置信度较低，建议以官网最新信息为准。",
            "confidence": "low",
            "sources": [],
            "attachments": [],
            "tools_used": [],
            "fallback": True,
            "session_id": None,
        }
