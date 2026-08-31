"""Hybrid 查询规划器。

规划器负责语义理解和结构化决策；权限、检索器白名单和资源上限由本模块
在服务端再次校验。没有可用 LLM 时只启用少量高精度规则作为保守降级。
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import BaseModel, Field

from backend.config import settings
from backend.rag.contracts import RetrievalPlan, RetrievalTarget, SubQuestion

__all__ = ["QueryPlanner", "RetrievalPlan", "RetrievalTarget", "SubQuestion"]


TOOL_TARGETS: set[str] = {
    "download_search", "contact_search", "service_link_search", "major_search",
    "job_search", "news_search", "weather_search", "map_route", "academic_search",
}


class PlannerLLMOutput(BaseModel):
    standalone_query: str = ""
    language: str = "zh"
    subquestions: list[SubQuestion] = Field(default_factory=list, max_length=5)
    retrievers: list[RetrievalTarget] = Field(default_factory=list, max_length=12)
    planner_reason: str = ""


PLANNER_SYSTEM_PROMPT = """你是仲恺农业工程学院校园信息服务的查询理解器。
请把用户当前问题结合最近对话改写为可独立检索的问题，并拆成 1 到 5 个独立子问题。
只选择真正需要的检索目标，不要因为用户已登录就选择 user_docs。

可选检索目标：campus_rag、shared_docs、user_docs、download_search、contact_search、
service_link_search、major_search、job_search、news_search、weather_search、map_route、academic_search。

user_docs 仅在用户明确提到“我的文档/我上传的/这份文件/根据我的培养方案”等私有上下文时选择。
天气和路线等纯实时问题不要默认加入 campus_rag。每个子问题最多选择 4 个检索目标。
entities 可填写 campus、date、department、major_name、document_type 等字段，filters 只填必要过滤条件。
planner_reason 用一句短话说明意图和是否使用历史，不要生成答案。"""


class QueryPlanner:
    """一次结构化 LLM 规划 + 保守规则降级。"""

    _WEATHER = ("天气", "气温", "温度", "下雨", "下雪", "带伞", "雨具")
    _ROUTE = ("怎么去", "怎么走", "路线", "导航", "坐地铁", "坐公交", "到哪里", "多远", "交通方式", "前往")
    _JOB = ("招聘会", "双选会", "宣讲会", "来学校宣讲", "招聘", "就业机会", "找工作")
    _NEWS = ("通知", "公告", "新闻", "最近发了什么", "学校动态", "最新动态", "校园资讯", "消息", "公布")
    _CONTACT = ("电话", "联系方式", "报障", "报修", "维修", "故障", "校医院", "医保", "找谁", "联系谁", "怎么联系")
    _SERVICE = ("入口", "登录", "网址", "链接", "oa", "vpn", "邮箱", "系统", "办事大厅")
    _DOWNLOAD = ("下载", "申请表", "表格", "材料", "办理", "学生证", "休学", "学籍异动")
    _MAJOR = ("专业", "学院", "培养方案", "专业目录", "专业代码")
    _ACADEMIC = ("论文", "文献", "参考文献", "学术搜索")
    _PRIVATE = (
        "我的文档", "我上传的", "上传的文档", "这份文件", "这份文档",
        "这份培养方案", "我的培养方案", "根据我的培养方案", "根据培养方案", "私有知识库",
    )

    def __init__(self) -> None:
        self._structured_llm: Any = None
        self._init_llm()

    def _init_llm(self) -> None:
        if settings.query_planner_mode == "rule_fallback" or not settings.deepseek_api_key:
            return
        try:
            from langchain_deepseek import ChatDeepSeek

            llm = ChatDeepSeek(
                model=settings.query_planner_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=0.0,
                max_tokens=1200,
            )
            self._structured_llm = llm.with_structured_output(PlannerLLMOutput)
        except Exception as exc:
            print(f"[QueryPlanner] LLM 初始化失败，将使用规则降级: {exc}")

    @property
    def available(self) -> bool:
        return self._structured_llm is not None

    @staticmethod
    def normalize(query: str) -> str:
        normalized = re.sub(r"\s+", "", query or "").strip()
        normalized = re.sub(r"[？?！!。]+$", "", normalized)
        return normalized or (query or "").strip()

    @classmethod
    def rewrite_for_retry(
        cls,
        query: str,
        missing_information: list[str] | None = None,
        conflicts: list[str] | None = None,
    ) -> str:
        """基于 Judge 缺口生成一次定向重试查询，保留原查询中的实体和年份。"""
        base = cls.normalize(query)
        missing = [
            str(item).replace("未覆盖：", "").strip()
            for item in (missing_information or [])
            if str(item).strip()
        ]
        constraints = list(dict.fromkeys(missing[:5]))
        if conflicts:
            constraints.append("排除冲突适用对象或文档类型")
        if not constraints:
            return base
        return f"{base}；补充检索约束：{'、'.join(constraints)}"

    def plan(
        self,
        question: str,
        *,
        history: list[dict[str, str]] | None = None,
        user_id: int | None = None,
        context_hint: str | None = None,
    ) -> RetrievalPlan:
        """返回一个可直接使用、也可 await 的计划。

        计划对象的 await 兼容桥让旧的同步调用方可以平滑迁移；Controller
        会 await 它，因此启用 LLM 时仍只进行一次异步结构化调用。
        """
        fallback = self._rule_plan(question, history=history, user_id=user_id, context_hint=context_hint)
        if not self.available:
            return fallback

        async def resolve() -> RetrievalPlan:
            try:
                from langchain_core.messages import HumanMessage, SystemMessage

                output = await self._structured_llm.ainvoke([
                    SystemMessage(content=PLANNER_SYSTEM_PROMPT),
                    HumanMessage(content=f"最近对话：\n{self._history_text(history) or '无'}\n当前问题：{question}"),
                ])
                return self._validate_llm_plan(
                    question, output, fallback=fallback, history=history,
                    user_id=user_id, context_hint=context_hint,
                )
            except Exception as exc:
                fallback.planner_reason = f"LLM 规划不可用，已保守降级：{type(exc).__name__}"
                return fallback

        fallback._deferred = resolve  # type: ignore[attr-defined]
        return fallback

    def _rule_plan(
        self,
        question: str,
        *,
        history: list[dict[str, str]] | None,
        user_id: int | None,
        context_hint: str | None,
    ) -> RetrievalPlan:
        original = question or ""
        standalone, used_history = self._standalone_query(original, history)
        private_requested = self._private_requested(original, context_hint, history)
        pairs = self._rule_subquestions(standalone)
        if not pairs:
            pairs = [(standalone, "general", ["campus_rag"], {})]

        subquestions: list[SubQuestion] = []
        for index, (query, intent, retrievers, entities) in enumerate(pairs[: settings.rag_max_subquestions], 1):
            selected = list(dict.fromkeys(retrievers))[:4]
            if private_requested and (self._is_private_query(query) or self._hint_is_private(context_hint)):
                selected = ["user_docs"]
            requires_private = private_requested and any(r == "user_docs" for r in selected)
            if private_requested and "user_docs" not in selected and self._is_private_query(query):
                selected = [*selected[:3], "user_docs"]
                requires_private = True
            selected = self._scope_retrievers(selected, user_id=user_id, private_requested=private_requested)
            subquestions.append(SubQuestion(
                id=f"q{index}", query=query, intent=intent, retrievers=selected,
                entities=entities, requires_private_context=requires_private,
            ))

        intents = {subq.intent for subq in subquestions}
        if {"weather", "route"}.issubset(intents) and subquestions:
            # 组合行程问题可保留校园知识库作为地点上下文；单独天气/路线不加入。
            first = subquestions[0]
            if "campus_rag" not in first.retrievers:
                first.retrievers.append("campus_rag")

        retrievers = list(dict.fromkeys(r for subq in subquestions for r in subq.retrievers))
        reason = "规则降级：仅选择高精度意图目标"
        if used_history:
            reason += "；已结合最近对话补全当前问题"
        if private_requested and user_id is None:
            reason += "；检测到私有文档意图但当前未登录，需要登录后检索"
        return RetrievalPlan(
            original_query=original, standalone_query=standalone, subquestions=subquestions,
            retrievers=retrievers, used_history=used_history, planner_source="rule_fallback",
            planner_reason=reason, trace_id=uuid.uuid4().hex,
        )

    def _rule_subquestions(self, query: str) -> list[tuple[str, str, list[str], dict[str, str]]]:
        lowered = query.lower()
        found: list[tuple[str, str, list[str], dict[str, str]]] = []

        def add(intent: str, targets: list[str], entities: dict[str, str] | None = None) -> None:
            found.append((query, intent, targets, entities or {}))

        weather_request = any(word in lowered for word in self._WEATHER) and (
            any(marker in query for marker in ("吗", "如何", "怎么样", "多少", "带伞", "下雨", "气温", "温度"))
            or query.strip().endswith(("天气", "气温", "温度"))
        )
        if weather_request:
            add("weather", ["weather_search"], {"date": "tomorrow" if "明天" in query else "today" if "今天" in query else ""})
        if any(word in lowered for word in self._ROUTE):
            add("route", ["map_route"], self._extract_campuses(query))
        if any(word in lowered for word in self._JOB):
            add("job", ["job_search"])
        if any(word in lowered for word in self._NEWS):
            add("news", ["news_search"])
        if any(word in lowered for word in self._CONTACT):
            entities = {}
            for campus in ("白云校区", "海珠校区"):
                if campus in query:
                    entities["campus"] = campus
            contact_targets = ["contact_search", "service_link_search"] if "入口" in query or "网络" in query else ["contact_search"]
            add("contact", [*contact_targets, "campus_rag"], entities)
        if any(word in lowered for word in self._SERVICE):
            add("service", ["service_link_search"])
        if any(word in lowered for word in self._DOWNLOAD) and "下载速度" not in query:
            add("download", ["download_search", "campus_rag"])
        if any(word in lowered for word in self._MAJOR):
            add("major", ["major_search", "campus_rag"])
        if any(word in lowered for word in self._ACADEMIC):
            add("academic", ["academic_search"])

        if "分别" in query and any(mark in query for mark in ("材料", "地点", "电话")):
            found = []
            for label, terms, targets in (
                ("materials", ("材料",), ["campus_rag", "download_search"]),
                ("location", ("地点", "哪里"), ["campus_rag"]),
                ("contact", ("电话", "联系"), ["contact_search"]),
            ):
                if any(term in query for term in terms):
                    found.append((f"{query}（查询{label}）", label, targets, {}))
        return found

    def _validate_llm_plan(
        self,
        question: str,
        output: PlannerLLMOutput | dict[str, Any],
        *,
        fallback: RetrievalPlan,
        history: list[dict[str, str]] | None,
        user_id: int | None,
        context_hint: str | None,
    ) -> RetrievalPlan:
        parsed = output if isinstance(output, PlannerLLMOutput) else PlannerLLMOutput.model_validate(output)
        standalone = self.normalize(parsed.standalone_query) or fallback.standalone_query
        private_requested = self._private_requested(question, context_hint, history)
        subquestions: list[SubQuestion] = []
        for index, raw in enumerate(parsed.subquestions[: settings.rag_max_subquestions], 1):
            query = self.normalize(raw.query)[:500] or standalone
            selected = [name for name in raw.retrievers if name in TOOL_TARGETS or name in {"campus_rag", "shared_docs", "user_docs"}]
            selected = list(dict.fromkeys(selected))[:4]
            if not (private_requested and user_id is not None):
                selected = [name for name in selected if name != "user_docs"]
                if private_requested and (self._is_private_query(query) or self._hint_is_private(context_hint)):
                    selected = [name for name in selected if name not in {"shared_docs", "campus_rag"}]
            if not selected:
                private_guest = private_requested and user_id is None and (
                    self._is_private_query(query) or self._hint_is_private(context_hint)
                )
                selected = [] if private_guest else (
                    ["campus_rag"] if not self._is_realtime_query(query) else fallback.subquestions[0].retrievers
                )
            entities = {str(k): str(v)[:100] for k, v in raw.entities.items() if str(v).strip()}
            subquestions.append(raw.model_copy(update={
                "id": f"q{index}", "query": query, "retrievers": selected,
                "entities": entities,
                "requires_private_context": private_requested and "user_docs" in selected,
            }))
        if not subquestions:
            return fallback
        retrievers = list(dict.fromkeys(r for subq in subquestions for r in subq.retrievers))
        reason = (parsed.planner_reason or "LLM 完成查询改写、意图识别和问题分解")[:300]
        if private_requested and user_id is None:
            reason += "；私有文档需要登录"
        return RetrievalPlan(
            original_query=question, standalone_query=standalone, language=parsed.language or "zh",
            subquestions=subquestions, retrievers=retrievers, used_history=bool(history),
            planner_source="llm", planner_reason=reason, trace_id=fallback.trace_id,
        )

    def _scope_retrievers(self, retrievers: list[str], *, user_id: int | None, private_requested: bool) -> list[str]:
        scoped = [r for r in retrievers if r != "user_docs" or (private_requested and user_id is not None)]
        return scoped or (["campus_rag"] if not retrievers else [])

    def _private_requested(self, question: str, context_hint: str | None, history: list[dict[str, str]] | None) -> bool:
        text = " ".join([question or "", context_hint or "", self._history_text(history)])
        return self._is_private_query(text) or self._hint_is_private(context_hint)

    def _is_private_query(self, text: str) -> bool:
        return any(term in text for term in self._PRIVATE)

    @staticmethod
    def _hint_is_private(context_hint: str | None) -> bool:
        hint = (context_hint or "").lower()
        return any(term in hint for term in ("private", "personal", "user-doc", "knowledge-base", "个人知识库", "私有文档"))

    @staticmethod
    def _is_realtime_query(query: str) -> bool:
        return any(term in query for term in ("天气", "下雨", "带伞", "路线", "怎么去", "怎么走", "导航"))

    def _standalone_query(self, question: str, history: list[dict[str, str]] | None) -> tuple[str, bool]:
        current = self.normalize(question)
        if not history or not self._is_elliptical(current):
            return current, False
        previous = next((str(item.get("content") or "").strip() for item in reversed(history) if item.get("content")), "")
        if not previous:
            return current, False
        previous = self.normalize(previous)
        previous = re.sub(r"^(用户|助手)[:：]", "", previous)
        return f"{previous}；当前追问：{current}", True

    @staticmethod
    def _is_elliptical(query: str) -> bool:
        return any(term in query for term in ("那", "条件呢", "怎么下载", "怎么申请", "明天呢", "呢", "条件", "地点")) and len(query) <= 18

    @staticmethod
    def _extract_campuses(query: str) -> dict[str, str]:
        campuses = re.findall(r"(广州南站|广州东站|海珠校区|白云校区|海珠|白云)", query)
        entities: dict[str, str] = {}
        if campuses:
            entities["origin"] = campuses[0]
        if len(campuses) > 1:
            entities["destination"] = campuses[1]
        return entities

    @staticmethod
    def _history_text(history: list[dict[str, str]] | None) -> str:
        if not history:
            return ""
        return "\n".join(f"{item.get('role', 'user')}: {item.get('content', '')}" for item in history[-6:])
