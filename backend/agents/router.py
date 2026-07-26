"""Agent 路由模块。

负责意图识别，决定调用 RAG、智能文档、结构化工具或混合路径。
第一版使用规则路由，后续可升级为 LLM 路由。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.config import settings

PathType = Literal["general_rag", "document_rag", "tool", "hybrid", "fallback"]


class IntentResult(BaseModel):
    """意图识别结果。"""

    path: PathType
    tool: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    intent_label: str = ""
    confidence: float = 1.0


# 关键词 → 路由规则（第一版规则路由）
_RULES: list[tuple[list[str], IntentResult]] = [
    (
        ["培养方案", "招生章程", "招生专业目录", "招生考试大纲", "这个文档", "总结", "摘要"],
        IntentResult(path="document_rag", intent_label="智能文档问答"),
    ),
    (
        ["申请表", "下载", "表格", "流程图", "学生证", "缓考", "免修", "重修", "学籍异动", "请假"],
        IntentResult(
            path="tool", tool="download_search", intent_label="资料下载查询"
        ),
    ),
    (
        ["电话", "联系方式", "联系", "报障", "维修科", "饮食科", "水电中心", "网络中心"],
        IntentResult(
            path="tool", tool="contact_search", intent_label="联系方式查询"
        ),
    ),
    (
        ["专业", "学院", "机构", "教学机构", "党政", "本科专业", "专业代码"],
        IntentResult(
            path="tool", tool="major_search", intent_label="专业学院查询"
        ),
    ),
    (
        ["入口", "登录", "OA", "邮箱", "VPN", "教务系统", "融合式门户", "资产", "人事系统"],
        IntentResult(
            path="tool", tool="service_link_search", intent_label="服务入口查询"
        ),
    ),
    (
        ["天气", "气温", "温度", "下雨", "下雪", "台风", "刮风", "要带伞", "穿什么", "冷不冷", "热不热"],
        IntentResult(
            path="tool", tool="weather_search", intent_label="天气查询"
        ),
    ),
    (
        ["论文", "文献", "学术搜索", "研究方向", "参考文献", "论文搜索", "前沿论文"],
        IntentResult(
            path="tool", tool="academic_search", intent_label="学术搜索"
        ),
    ),
]


class QuestionRouter:
    """问题路由器。"""

    def __init__(self) -> None:
        self.mode = settings.agent_router_mode

    def route(self, question: str) -> IntentResult:
        """根据问题文本判断意图。"""
        if self.mode == "llm":
            return self._route_by_llm(question)
        return self._route_by_rule(question)

    def _route_by_rule(self, question: str) -> IntentResult:
        """规则路由：关键词匹配。"""
        for keywords, intent in _RULES:
            if any(k in question for k in keywords):
                return intent.model_copy()
        # 默认走通用 RAG
        return IntentResult(path="general_rag", intent_label="通用问答")

    def _route_by_llm(self, question: str) -> IntentResult:
        """LLM 路由：调用大模型输出 JSON 路由结果。

        TODO: 实现 LLM 路由 Prompt，输出结构化 JSON。
        """
        # 第一版回退到规则路由
        return self._route_by_rule(question)
