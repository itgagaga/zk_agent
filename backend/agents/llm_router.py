"""LLM 意图路由模块。

使用 LangChain Structured Output，让大模型根据用户问题选择
RAG 路径或结构化工具，替代纯关键词匹配的局限。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.agents.router import IntentResult, RoutePlan, RouteMode
from backend.config import settings

ToolName = Literal[
    "major_search",
    "download_search",
    "contact_search",
    "service_link_search",
    "weather_search",
    "academic_search",
    "map_route",
]

TOOL_TO_LABEL: dict[str, str] = {
    "major_search": "专业学院查询",
    "download_search": "资料下载查询",
    "contact_search": "联系方式查询",
    "service_link_search": "服务入口查询",
    "weather_search": "天气查询",
    "academic_search": "学术搜索",
    "map_route": "路线规划",
}

PATH_TO_LABEL: dict[str, str] = {
    "general_rag": "通用问答",
    "document_rag": "智能文档问答",
}

ROUTER_SYSTEM_PROMPT = """你是仲恺农业工程学院校园信息服务智能体的意图路由器。

根据用户问题，选择一条或多条处理路径，并判断是否需要多 Agent 协作（collab）。

## 可选路径

1. general_rag — 学校概况、招生政策、后勤服务、办事说明等官网公开信息问答
2. document_rag — 培养方案、招生章程、用户上传文档的内容问答/摘要/课程分析
3. tool — 调用结构化工具，tool 字段必填，可选值：
   - major_search：学院、专业、专业代码查询
   - download_search：教务表格、申请表、流程图下载
   - contact_search：部门电话、联系方式、报障电话
   - service_link_search：VPN、邮箱、教务系统、融合门户等入口
   - weather_search：天气、气温、是否下雨/带伞
   - academic_search：论文、文献、学术前沿检索
   - map_route：校区间/校内外路线、导航、交通方式

## 协作模式（collab）判定

以下情况应设为 collab，并列出多个 intents：
- 办事流程复合问（怎么办、需要什么材料、找谁、表格在哪）
- 用户显式多问（并、还有、以及、顺便、同时）
- 文档解读 + 办事咨询组合
- 路线 + 天气组合（如到校一日规划）

简单单一意图用 fast，只返回 1 条 intent。

## 注意

- 用户换说法也要识别意图，例如「会不会下雨」→ weather_search
- 无明确工具需求的一般校园问答 → general_rag
- 不要编造工具名；不确定时用 general_rag
- confidence 表示你对路由判断的置信度（0~1）
"""


class LLMIntent(BaseModel):
    """LLM 输出的单条意图。"""

    path: Literal["general_rag", "document_rag", "tool"]
    tool: ToolName | None = None
    intent_label: str = ""
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)


class LLMRouteOutput(BaseModel):
    """LLM 结构化路由输出。"""

    mode: RouteMode = "fast"
    collab_reason: str = ""
    intents: list[LLMIntent] = Field(min_length=1, max_length=8)


class LLMRouter:
    """基于 DeepSeek + Structured Output 的意图路由器。"""

    def __init__(self) -> None:
        self.llm: Any = None
        self._structured_llm: Any = None
        self._init_llm()

    def _init_llm(self) -> None:
        if not settings.deepseek_api_key:
            return
        try:
            from langchain_deepseek import ChatDeepSeek

            self.llm = ChatDeepSeek(
                model=settings.deepseek_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=0.0,
                max_tokens=600,
            )
            self._structured_llm = self.llm.with_structured_output(LLMRouteOutput)
        except Exception as exc:
            print(f"[LLMRouter] LLM 初始化失败: {exc}")

    @property
    def available(self) -> bool:
        return self._structured_llm is not None

    async def route(self, question: str) -> RoutePlan | None:
        """调用 LLM 进行意图路由，失败时返回 None。"""
        if self._structured_llm is None:
            return None

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content=ROUTER_SYSTEM_PROMPT),
                HumanMessage(content=f"用户问题：{question}"),
            ]
            output: LLMRouteOutput = await self._structured_llm.ainvoke(messages)
            return self._to_route_plan(output)
        except Exception as exc:
            print(f"[LLMRouter] 路由失败，将回退规则: {exc}")
            return None

    def _to_route_plan(self, output: LLMRouteOutput) -> RoutePlan:
        intents: list[IntentResult] = []
        seen: set[str] = set()

        for item in output.intents:
            tool = item.tool if item.path == "tool" else None
            if item.path == "tool" and tool not in TOOL_TO_LABEL:
                continue

            key = tool or item.path
            if key in seen:
                continue
            seen.add(key)

            label = item.intent_label.strip()
            if not label:
                label = TOOL_TO_LABEL.get(tool or "", PATH_TO_LABEL.get(item.path, "通用问答"))

            path: str = item.path
            if output.mode == "collab" and item.path == "tool":
                path = "hybrid"

            intents.append(
                IntentResult(
                    path=path,  # type: ignore[arg-type]
                    tool=tool,
                    intent_label=label,
                    confidence=item.confidence,
                )
            )

        if not intents:
            intents = [IntentResult(path="general_rag", intent_label="通用问答", confidence=0.5)]

        if output.mode == "fast" and len(intents) > 1:
            intents = [intents[0]]

        return RoutePlan(
            mode=output.mode,
            intents=intents,
            collab_reason=output.collab_reason,
        )
