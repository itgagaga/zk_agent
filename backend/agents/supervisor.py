"""兼容性 Supervisor 模块。

新请求路径由 ``RetrievalManager`` 和 ``EvidenceGate`` 统一融合、门控证据，
本模块仅保留给旧调用方和历史数据兼容，不参与 ``AgentController`` 的运行时编排。

在子 Agent 取证完成后，决定本次回答应优先基于：
- api：实时第三方 API（地图、天气）
- tool：结构化查询（电话、专业、下载、入口）
- rag：官网 / 向量检索资料
- document：用户上传文档
- affairs：办事多 Agent 融合（材料 + 联系 + 入口 + 政策）

决策结果会**结构性过滤**传给 AnswerGenerator 的证据，而非仅靠 Prompt 约束。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.agents.router import RoutePlan

EvidencePriority = Literal["api", "tool", "rag", "document", "affairs", "composite"]

# 实时 API 类 Agent
_LIVE_API_TOOLS = frozenset({"map_route", "weather_search"})

# 结构化查询 Agent
_STRUCTURED_TOOLS = frozenset({
    "download_search", "contact_search", "service_link_search", "major_search",
})

# 办事类 collab 原因
_AFFAIRS_COLLAB_REASONS = frozenset({
    "办事流程复合问", "多办事域命中", "文档与办事组合",
})

# 综合多域 collab：需融合文档 + 资料 + API + 结构化查询
_COMPOSITE_COLLAB_REASONS = frozenset({"综合多意图", "显式多意图"})

# 学业咨询关键词 → 需文档 Agent
_ADVISORY_KEYWORDS = [
    "建议", "信计", "计科", "信息与计算", "学习", "就业", "发展",
    "培养方案", "课程", "修读", "职业规划",
]


class SupervisorDecision(BaseModel):
    """Supervisor 对证据优先级的裁决。"""

    priority: EvidencePriority
    reason: str = ""
    active_agents: list[str] = Field(default_factory=list)
    use_rag: bool = False
    use_doc: bool = False
    api_tools: list[str] = Field(default_factory=list)


class EvidenceSupervisor:
    """证据优先级 Supervisor：分析各 Agent 取证结果，裁决生成策略。"""

    def decide(self, evidence: dict[str, Any], plan: RoutePlan) -> SupervisorDecision:
        """根据取证结果与路由计划，决定证据优先级。"""
        tool_results: list[dict[str, Any]] = evidence.get("tool_results") or []
        if not tool_results and evidence.get("tool_result"):
            tool_results = [evidence["tool_result"]]

        live_api_hits = [
            tr for tr in tool_results
            if tr.get("tool") in _LIVE_API_TOOLS and tr.get("items")
        ]
        structured_hits = [
            tr for tr in tool_results
            if tr.get("tool") in _STRUCTURED_TOOLS and tr.get("items")
        ]
        has_rag = bool(evidence.get("rag_hits"))
        has_doc = bool(evidence.get("doc_hits"))
        has_document_intent = any(
            i.path == "document_rag" for i in plan.intents
        )

        active = [i.intent_label for i in plan.intents if i.intent_label]
        question = evidence.get("question", "")

        # 0. 用户上传文档已命中 → 优先文档，避免 composite/官网索引误导（如信计培养方案）
        if has_doc and (
            has_document_intent
            or any(k in question for k in _ADVISORY_KEYWORDS)
        ):
            return SupervisorDecision(
                priority="document",
                reason="用户上传文档已命中，优先基于私有文档回答",
                active_agents=active or ["智能文档问答"],
                use_rag=False,
                use_doc=True,
            )

        # 1. 综合多意图 → composite 融合（文档 + 资料 + API + 工具，分区作答）
        if plan.mode == "collab" and plan.collab_reason in _COMPOSITE_COLLAB_REASONS:
            return SupervisorDecision(
                priority="composite",
                reason="综合多意图，分区融合文档/资料/API/结构化查询",
                active_agents=active,
                use_rag=True,
                use_doc=True,
            )

        # 2. 办事多 Agent 协作 → affairs 融合
        if plan.mode == "collab" and plan.collab_reason in _AFFAIRS_COLLAB_REASONS:
            return SupervisorDecision(
                priority="affairs",
                reason="办事多 Agent 协作，融合材料/联系/入口/政策",
                active_agents=active,
                use_rag=True,
                use_doc=True,
            )

        # 2. 实时 API 有有效数据 → api 优先（纯路线/天气场景）
        if live_api_hits:
            api_names = [tr.get("tool", "") for tr in live_api_hits]
            # 路线+天气组合，或单一地图/天气问题
            if not structured_hits and not has_document_intent:
                return SupervisorDecision(
                    priority="api",
                    reason="实时 API Agent 已返回有效数据，优先基于 API 回答",
                    active_agents=[tr.get("tool", "") for tr in live_api_hits],
                    use_rag=False,
                    use_doc=False,
                    api_tools=api_names,
                )
            # API + 其他工具混合：API 部分仍优先，但保留结构化结果
            if structured_hits:
                return SupervisorDecision(
                    priority="tool",
                    reason="结构化查询 + 实时 API 混合，以结构化与 API 为准",
                    active_agents=active,
                    use_rag=False,
                    use_doc=False,
                    api_tools=api_names,
                )

        # 3. 智能文档问答 → document 优先
        if has_document_intent and (has_doc or has_rag):
            return SupervisorDecision(
                priority="document",
                reason="文档 Agent 命中，优先基于上传文档与知识库",
                active_agents=active or ["智能文档问答"],
                use_rag=True,
                use_doc=True,
            )

        # 4. 结构化工具命中 → tool 优先
        if structured_hits:
            use_rag = has_rag and plan.mode == "collab"
            return SupervisorDecision(
                priority="tool",
                reason="结构化 Agent 已返回结果，优先基于查询结果"
                + ("，官网资料作补充" if use_rag else ""),
                active_agents=[tr.get("tool", "") for tr in structured_hits],
                use_rag=use_rag,
                use_doc=has_doc,
            )

        # 5. 学术搜索等有结果的外部工具
        other_tool_hits = [
            tr for tr in tool_results
            if tr.get("tool") not in _LIVE_API_TOOLS
            and tr.get("tool") not in _STRUCTURED_TOOLS
            and tr.get("items")
        ]
        if other_tool_hits:
            return SupervisorDecision(
                priority="tool",
                reason=f"{other_tool_hits[0].get('tool')} Agent 已返回结果",
                active_agents=[tr.get("tool", "") for tr in other_tool_hits],
                use_rag=has_rag,
                use_doc=has_doc,
            )

        # 6. API 调用失败但有 RAG → 回退到资料
        api_errors = [
            tr for tr in tool_results
            if tr.get("tool") in _LIVE_API_TOOLS and not tr.get("items")
        ]
        if api_errors and has_rag:
            return SupervisorDecision(
                priority="rag",
                reason="实时 API 未返回有效数据，回退至官网资料",
                active_agents=["政策解读"],
                use_rag=True,
                use_doc=has_doc,
            )

        # 7. 仅 API 失败无 RAG → 仍走 api 通道，让生成器报 API 错误
        if api_errors:
            return SupervisorDecision(
                priority="api",
                reason="实时 API 调用失败，基于 API 错误信息回答",
                active_agents=[tr.get("tool", "") for tr in api_errors],
                use_rag=False,
                use_doc=False,
                api_tools=[tr.get("tool", "") for tr in api_errors],
            )

        # 8. 默认 RAG
        return SupervisorDecision(
            priority="rag",
            reason="基于官网资料回答",
            active_agents=active or ["政策解读"],
            use_rag=True,
            use_doc=has_doc,
        )

    @staticmethod
    def apply(evidence: dict[str, Any], decision: SupervisorDecision) -> dict[str, Any]:
        """按 Supervisor 裁决，结构性过滤传给生成器的证据。"""
        filtered = dict(evidence)
        filtered["evidence_priority"] = decision.priority
        filtered["supervisor_reason"] = decision.reason
        filtered["supervisor_agents"] = decision.active_agents

        if not decision.use_rag:
            filtered.pop("rag_hits", None)
        if not decision.use_doc:
            filtered.pop("doc_hits", None)

        # affairs / tool / api 模式保留全部 tool_results
        tool_results: list[dict] = evidence.get("tool_results") or []
        if not tool_results and evidence.get("tool_result"):
            tool_results = [evidence["tool_result"]]

        if decision.priority == "api" and decision.api_tools:
            tool_results = [
                tr for tr in tool_results
                if tr.get("tool") in decision.api_tools or tr.get("tool") in _LIVE_API_TOOLS
            ]

        if tool_results:
            filtered["tool_results"] = tool_results
            filtered["tool_result"] = tool_results[0]
        else:
            filtered.pop("tool_results", None)
            filtered.pop("tool_result", None)

        return filtered

    def should_fetch_rag(self, evidence: dict[str, Any], plan: RoutePlan) -> bool:
        """Supervisor 判断是否需要调用 RAG Agent 取证。"""
        if plan.mode == "collab" and plan.collab_reason in _COMPOSITE_COLLAB_REASONS:
            return True
        if any(i.path in ("general_rag", "document_rag") for i in plan.intents):
            return True
        if plan.mode == "collab" and plan.collab_reason in _AFFAIRS_COLLAB_REASONS:
            return True

        question = evidence.get("question", "")
        if any(k in question for k in _ADVISORY_KEYWORDS):
            return True

        tool_results: list[dict] = evidence.get("tool_results") or []
        live_planned = any(
            i.tool in _LIVE_API_TOOLS for i in plan.intents if i.tool
        )
        live_ok = any(
            tr.get("tool") in _LIVE_API_TOOLS and tr.get("items")
            for tr in tool_results
        )
        # 实时 API 已成功 → 不需要 RAG
        if live_planned and live_ok:
            return False
        # 实时 API 计划了但失败 → 回退 RAG
        if live_planned and not live_ok:
            return True
        # 无工具命中，走 RAG
        if not tool_results and plan.primary.path in ("general_rag", "document_rag", "hybrid"):
            return True
        return False

    def should_fetch_doc(
        self,
        evidence: dict[str, Any],
        plan: RoutePlan,
        *,
        user_id: int | None = None,
    ) -> bool:
        """Supervisor 判断是否需要调用文档库 Agent。"""
        if user_id is not None:
            return True
        question = evidence.get("question", "")
        if plan.mode == "collab" and plan.collab_reason in _COMPOSITE_COLLAB_REASONS:
            return True
        if any(i.path == "document_rag" for i in plan.intents):
            return True
        if plan.mode == "collab" and plan.collab_reason in _AFFAIRS_COLLAB_REASONS:
            return True
        if any(k in question for k in _ADVISORY_KEYWORDS):
            return True
        return False
