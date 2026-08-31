"""兼容性路由模块。

新请求路径由 ``QueryPlanner`` 负责声明式规划，``QuestionRouter`` 仅供
旧分析脚本和外部调用方兼容使用，不参与 ``AgentController`` 的运行时编排。

负责意图识别与复杂度判定：
- fast：简单问题，单路径低延迟
- collab：复杂办事问题，多 Agent 并行协作
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PathType = Literal["general_rag", "document_rag", "tool", "hybrid", "fallback"]
RouteMode = Literal["fast", "collab"]
RouterSource = Literal["rule", "planner", "rule_fallback"]

# 办事协作 Agent 组（材料 / 联系 / 入口）
_AFFAIRS_TOOLS = frozenset({"download_search", "contact_search", "service_link_search"})

# 独立工具：有结果时可跳过 RAG，降低延迟
_STANDALONE_TOOLS = frozenset(
    {"map_route", "weather_search", "contact_search", "major_search", "service_link_search"}
)

# 办事流程关键词：命中 + 办事工具 → 协作模式
_AFFAIR_PROCESS_KEYWORDS = [
    "怎么办", "怎么申请", "怎么办理", "怎么填报", "如何申请", "如何办理",
    "流程", "步骤", "需要什么", "需要哪些", "要什么材料", "哪些材料",
    "找谁", "找哪个", "去哪里办", "在哪办", "在哪个系统",
]

# 显式多意图连接词
_MULTI_INTENT_CONNECTORS = ["并", "还有", "以及", "顺便", "同时", "另外", "另外还要"]

# 学业/专业咨询关键词 → 需文档 Agent 参与
_ADVISORY_KEYWORDS = [
    "建议", "信计", "计科", "信息与计算", "学习", "就业", "发展",
    "培养方案", "课程", "修读", "职业规划",
]

# 综合多意图 collab 原因
_COMPOSITE_COLLAB_REASONS = frozenset({"综合多意图", "显式多意图"})

# 关键词 → 路由规则
_RULES: list[tuple[list[str], IntentResult]] = []  # forward ref, defined after IntentResult


class IntentResult(BaseModel):
    """单条意图识别结果。"""

    path: PathType
    tool: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    intent_label: str = ""
    confidence: float = 1.0


class RoutePlan(BaseModel):
    """路由计划：自适应单路径或多 Agent 协作。"""

    mode: RouteMode = "fast"
    intents: list[IntentResult] = Field(default_factory=list)
    collab_reason: str = ""
    router_source: RouterSource = "rule"

    @property
    def primary(self) -> IntentResult:
        """主意图（兼容旧逻辑）。"""
        if self.intents:
            return self.intents[0]
        return IntentResult(path="general_rag", intent_label="通用问答")


# 关键词 → 路由规则（IntentResult 定义后初始化）
_RULES = [
    (
        ["培养方案", "招生章程", "招生专业目录", "招生考试大纲", "这个文档", "总结", "摘要",
         "信计", "计科", "有什么建议", "给点建议", "课程", "课表", "必修", "选修", "学分", "信息与计算"],
        IntentResult(path="document_rag", intent_label="智能文档问答"),
    ),
    (
        ["申请表", "下载", "表格", "流程图", "学生证", "缓考", "免修", "重修", "学籍异动", "请假", "就业", "协议"],
        IntentResult(path="tool", tool="download_search", intent_label="资料下载查询"),
    ),
    (
        ["电话", "联系方式", "联系", "报障", "维修科", "饮食科", "水电中心", "网络中心"],
        IntentResult(path="tool", tool="contact_search", intent_label="联系方式查询"),
    ),
    (
        ["专业", "学院有", "教学机构", "党政", "本科专业", "专业代码", "有哪些专业", "专业有哪些", "信计", "计科"],
        IntentResult(path="tool", tool="major_search", intent_label="专业学院查询"),
    ),
    (
        ["入口", "登录", "OA", "邮箱", "VPN", "教务系统", "融合式门户", "资产", "人事系统", "校园网", "办网络", "网络报障"],
        IntentResult(path="tool", tool="service_link_search", intent_label="服务入口查询"),
    ),
    (
        ["天气", "气温", "温度", "下雨", "下雪", "台风", "刮风", "要带伞", "穿什么", "冷不冷", "热不热"],
        IntentResult(path="tool", tool="weather_search", intent_label="天气查询"),
    ),
    (
        ["论文", "文献", "学术搜索", "研究方向", "参考文献", "论文搜索", "前沿论文"],
        IntentResult(path="tool", tool="academic_search", intent_label="学术搜索"),
    ),
    (
        [
            "怎么去", "怎么走", "路线", "导航", "交通指引", "交通方式", "怎么坐车", "怎么过去",
            "坐公交", "坐地铁", "乘公交", "乘地铁",
            "驾车去", "开车去", "坐车去", "步行去", "骑行去",
            "多远", "多长时间", "多久到", "校区之间",
            "从广州", "从仲恺", "到白云校区", "到海珠校区",
            "白云校区怎么", "海珠校区怎么", "到仲恺", "前往学校", "到学校",
        ],
        IntentResult(path="tool", tool="map_route", intent_label="路线规划"),
    ),
]


class QuestionRouter:
    """旧路由兼容适配器。

    默认请求链路不再使用本类；主链路的唯一规划入口是
    :class:`backend.rag.query_planner.QueryPlanner`。这里保留同步规则接口，
    供离线分析脚本和历史调用方使用；异步 ``route`` 则转调 QueryPlanner，
    不再读取旧的 ``AGENT_ROUTER_MODE``，也不再加载独立的 LLM 路由模块。
    """

    def __init__(self) -> None:
        # 保留可写属性，避免旧脚本在迁移期因设置 mode 失败；该值不再控制生产链路。
        self.mode = "compatibility"

    def route_rule(self, question: str) -> RoutePlan:
        """同步规则路由（评测与离线分析用）。"""
        plan = self._route_by_rule(question)
        plan.router_source = "rule"
        return plan

    async def route(self, question: str) -> RoutePlan:
        """兼容异步入口：委托唯一的 QueryPlanner 并映射为旧 RoutePlan。"""
        from backend.rag.query_planner import QueryPlanner

        retrieval_plan = await QueryPlanner().plan(question)
        return self._from_retrieval_plan(retrieval_plan)

    @staticmethod
    def _from_retrieval_plan(retrieval_plan: Any) -> RoutePlan:
        """将新检索计划转换成旧调用方可识别的 RoutePlan。"""
        label_map = {
            "major_search": "专业学院查询",
            "download_search": "资料下载查询",
            "contact_search": "联系方式查询",
            "service_link_search": "服务入口查询",
            "weather_search": "天气查询",
            "academic_search": "学术搜索",
            "map_route": "路线规划",
            "job_search": "就业信息查询",
            "news_search": "校园资讯查询",
            "campus_rag": "通用问答",
            "shared_docs": "智能文档问答",
            "user_docs": "智能文档问答",
        }
        intents: list[IntentResult] = []
        seen: set[str] = set()
        retrievers = [
            retriever
            for subquestion in retrieval_plan.subquestions
            for retriever in subquestion.retrievers
        ]
        for retriever in retrievers:
            if retriever in {"campus_rag", "shared_docs", "user_docs"}:
                path: PathType = "document_rag" if retriever != "campus_rag" else "general_rag"
                tool = None
            elif retriever in _STANDALONE_TOOLS or retriever in {
                "download_search", "academic_search", "job_search", "news_search"
            }:
                path = "tool"
                tool = retriever
            else:
                continue
            key = tool or path
            if key in seen:
                continue
            seen.add(key)
            intents.append(
                IntentResult(
                    path=path,
                    tool=tool,
                    intent_label=label_map.get(retriever, "通用问答"),
                )
            )
        if not intents:
            intents = [IntentResult(path="general_rag", intent_label="通用问答")]
        mode: RouteMode = "collab" if len(intents) > 1 else "fast"
        if mode == "collab":
            for intent in intents:
                if intent.path == "tool":
                    intent.path = "hybrid"
        return RoutePlan(
            mode=mode,
            intents=intents,
            collab_reason="兼容映射：QueryPlanner 多检索目标" if mode == "collab" else "",
            router_source="planner",
        )

    @staticmethod
    def _is_confident_rule_match(question: str, matched: list[IntentResult]) -> bool:
        """规则路由是否足够可信，无需 LLM 介入。"""
        if not matched:
            return False

        if len(matched) >= 2:
            if QuestionRouter._has_affair_process_keywords(question):
                return True
            if QuestionRouter._has_multi_intent_connectors(question):
                return True
            tool_set = {i.tool for i in matched if i.tool}
            if tool_set >= {"map_route", "weather_search"}:
                return True
            return False

        intent = matched[0]
        if intent.tool in _STANDALONE_TOOLS:
            return True
        if intent.path == "document_rag":
            return True
        if intent.tool in _AFFAIRS_TOOLS:
            return True
        return True

    def _match_all_intents(self, question: str) -> list[IntentResult]:
        """匹配所有命中的意图（去重）。"""
        matched: list[IntentResult] = []
        seen_tools: set[str | None] = set()
        seen_paths: set[str] = set()

        for keywords, intent in _RULES:
            if any(k in question for k in keywords):
                key = intent.tool or intent.path
                if key in seen_tools or (intent.path == "document_rag" and "document_rag" in seen_paths):
                    continue
                matched.append(intent.model_copy())
                seen_tools.add(intent.tool)
                if intent.path == "document_rag":
                    seen_paths.add("document_rag")
        return matched

    @staticmethod
    def _has_affair_process_keywords(question: str) -> bool:
        return any(k in question for k in _AFFAIR_PROCESS_KEYWORDS)

    @staticmethod
    def _has_multi_intent_connectors(question: str) -> bool:
        return any(c in question for c in _MULTI_INTENT_CONNECTORS)

    def _build_affairs_collab_intents(self, matched: list[IntentResult]) -> list[IntentResult]:
        """办事协作：材料 + 联系 + 入口 + 政策 RAG。"""
        label_map = {
            "download_search": "资料下载查询",
            "contact_search": "联系方式查询",
            "service_link_search": "服务入口查询",
        }
        intents = [
            IntentResult(path="tool", tool=tool, intent_label=label_map[tool])
            for tool in ("download_search", "contact_search", "service_link_search")
        ]
        intents.append(IntentResult(path="general_rag", intent_label="政策解读"))
        return intents

    @staticmethod
    def _has_advisory_keywords(question: str) -> bool:
        return any(k in question for k in _ADVISORY_KEYWORDS)

    @staticmethod
    def _has_multi_clauses(question: str) -> bool:
        """多子句复合问（中文逗号分隔）。"""
        return question.count("，") >= 2 or question.count(",") >= 2

    def _build_composite_intents(self, question: str, matched: list[IntentResult]) -> list[IntentResult]:
        """综合多意图：合并所有命中 Agent，并补齐文档/RAG/专业/入口。"""
        intents = list(matched)
        seen = {i.tool or i.path for i in intents}

        if "document_rag" not in seen:
            intents.insert(0, IntentResult(path="document_rag", intent_label="智能文档问答"))
        if "general_rag" not in seen:
            intents.append(IntentResult(path="general_rag", intent_label="政策解读"))

        if self._has_advisory_keywords(question) and "major_search" not in seen:
            intents.append(IntentResult(path="tool", tool="major_search", intent_label="专业学院查询"))

        if ("校园网" in question or "办网络" in question) and "service_link_search" not in seen:
            intents.append(IntentResult(path="tool", tool="service_link_search", intent_label="服务入口查询"))

        if ("校园网" in question or "网络" in question) and "contact_search" not in seen:
            intents.append(IntentResult(path="tool", tool="contact_search", intent_label="联系方式查询"))

        return intents

    def _decide_mode(self, question: str, matched: list[IntentResult]) -> tuple[RouteMode, str, list[IntentResult]]:
        """判定 fast / collab 并返回最终意图列表。"""
        if not matched:
            return "fast", "", [IntentResult(path="general_rag", intent_label="通用问答")]

        affairs_matched = [i for i in matched if i.tool in _AFFAIRS_TOOLS]
        affairs_tools = {i.tool for i in affairs_matched}
        has_document = any(i.path == "document_rag" for i in matched)
        has_process = self._has_affair_process_keywords(question)
        has_connector = self._has_multi_intent_connectors(question)
        has_clauses = self._has_multi_clauses(question)
        has_advisory = self._has_advisory_keywords(question)
        tool_set = {i.tool for i in matched if i.tool}

        # 协作：办事流程问法（启动办事 Agent 组）
        if has_process:
            return "collab", "办事流程复合问", self._build_affairs_collab_intents(matched)

        # 协作：多办事域命中
        if len(affairs_tools) >= 2:
            return "collab", "多办事域命中", self._build_affairs_collab_intents(matched)

        # 协作：综合多意图（多子句 / 咨询 + API / 多域混合）
        if has_clauses or (has_advisory and len(matched) >= 1) or len(matched) >= 3:
            return "collab", "综合多意图", self._build_composite_intents(question, matched)

        # 协作：连接词 + 多意图命中
        if has_connector and len(matched) >= 2:
            return "collab", "显式多意图", self._build_composite_intents(question, matched)

        # 协作：文档 + 办事
        if has_document and affairs_matched:
            intents = list(matched)
            if not any(i.path == "general_rag" for i in intents):
                intents.append(IntentResult(path="general_rag", intent_label="政策解读"))
            return "collab", "文档与办事组合", intents

        # 到校一日：纯路线 + 天气（无其他域）
        if tool_set >= {"map_route", "weather_search"} and len(matched) <= 2:
            return "collab", "路线与天气组合", matched

        # 默认 fast：只取优先级最高的一条（规则表顺序）
        return "fast", "", [matched[0]]

    def _route_by_rule(self, question: str) -> RoutePlan:
        """规则路由：关键词匹配 + 复杂度判定。"""
        matched = self._match_all_intents(question)
        mode, reason, intents = self._decide_mode(question, matched)

        if mode == "collab":
            for intent in intents:
                if intent.path == "tool":
                    intent.path = "hybrid"

        return RoutePlan(mode=mode, intents=intents, collab_reason=reason)


def is_standalone_tool(tool: str | None) -> bool:
    """是否为可独立回答、可跳过 RAG 的工具。"""
    return tool in _STANDALONE_TOOLS
