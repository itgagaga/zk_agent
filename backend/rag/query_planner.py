"""轻量查询规划器：选择可并行的检索器，不做互斥路由裁决。"""
from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import BaseModel, Field


class SubQuestion(BaseModel):
    id: str
    query: str
    intent: str = "general"
    retrievers: list[str] = Field(default_factory=list)


class RetrievalPlan(BaseModel):
    query: str
    normalized_query: str
    subquestions: list[SubQuestion] = Field(default_factory=list)
    retrievers: list[str] = Field(default_factory=list)
    allow_fallback: bool = True
    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex)


class QueryPlanner:
    """基于可解释关键词的 planner；LLM 只应作为未来的可选扩展。"""

    _TOOL_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
        ("download_search", ("申请表", "下载", "表格", "缓考", "学生证", "学籍异动"), "download"),
        ("contact_search", ("电话", "联系方式", "报障", "维修", "校医院"), "contact"),
        ("service_link_search", ("入口", "登录", "OA", "邮箱", "VPN", "网络报障"), "service"),
        ("major_search", ("专业", "专业目录", "培养方案", "学院"), "major"),
        ("academic_search", ("论文", "文献", "学术搜索", "参考文献"), "academic"),
        ("weather_search", ("天气", "气温", "温度", "下雨", "下雪"), "weather"),
        ("map_route", ("怎么去", "路线", "导航", "怎么走", "多久到"), "route"),
    )

    @staticmethod
    def normalize(query: str) -> str:
        normalized = re.sub(r"\s+", "", query).strip()
        normalized = re.sub(r"[？?！!。]+$", "", normalized)
        return normalized or query.strip()

    def plan(self, query: str, *, user_id: int | None = None) -> RetrievalPlan:
        normalized = self.normalize(query)
        retrievers = ["campus_rag"]
        intents: list[str] = []
        for tool, keywords, intent in self._TOOL_RULES:
            if any(keyword.lower() in normalized.lower() for keyword in keywords):
                retrievers.append(tool)
                intents.append(intent)
        if user_id is not None or any(
            token in normalized for token in ("我的文档", "上传的文档", "培养方案", "总结", "这份文档")
        ):
            retrievers.append("user_docs")
        # Keep the list stable for deterministic traces and tests.
        retrievers = list(dict.fromkeys(retrievers))
        subquestion = SubQuestion(
            id="q1",
            query=normalized,
            intent="+".join(intents) or "general",
            retrievers=retrievers,
        )
        return RetrievalPlan(
            query=query,
            normalized_query=normalized,
            subquestions=[subquestion],
            retrievers=retrievers,
        )
