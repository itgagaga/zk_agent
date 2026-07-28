"""Agent 主控模块。

自适应多 Agent 编排：
- Router：选择参与取证的子 Agent
- 子 Agent 并行取证
- Supervisor：裁决证据优先级（API / 资料 / 办事融合）
- AnswerGenerator：按 Supervisor 过滤后的证据生成回答
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from backend.agents.answer_generator import AnswerGenerator
from backend.agents.fallback import FallbackHandler
from backend.agents.router import QuestionRouter, RoutePlan
from backend.agents.supervisor import EvidenceSupervisor
from backend.rag.retriever import RAGRetriever
from backend.tools.contact_tool import ContactTool
from backend.tools.download_tool import DownloadTool
from backend.tools.major_tool import MajorTool
from backend.tools.service_link_tool import ServiceLinkTool
from backend.tools.weather_tool import WeatherTool
from backend.tools.academic_search_tool import AcademicSearchTool
from backend.tools.map_tool import MapTool


class AgentController:
    """Agent 主控。"""

    def __init__(self) -> None:
        self.router = QuestionRouter()
        self.supervisor = EvidenceSupervisor()
        self.retriever = RAGRetriever()
        self.answer_generator = AnswerGenerator()
        self.fallback = FallbackHandler()
        self.tools: dict[str, Any] = {
            "major_search": MajorTool(),
            "download_search": DownloadTool(),
            "contact_search": ContactTool(),
            "service_link_search": ServiceLinkTool(),
            "weather_search": WeatherTool(),
            "academic_search": AcademicSearchTool(),
            "map_route": MapTool(),
        }

    @staticmethod
    def _clean_query(question: str) -> str:
        """清洗查询文本，提高 RAG 检索准确率。"""
        q = re.sub(r"[？?]+$", "", question)
        patterns = [
            r"主要讲了什么内容$", r"主要讲了什么$", r"主要讲了哪些$",
            r"讲了什么$", r"说了什么$", r"主要介绍什么$", r"介绍.{0,2}$",
            r"是什么$", r"有哪些$", r"有什么$", r"是哪些$",
            r"在哪里$", r"在哪$", r"怎么申请$", r"怎么办理$", r"怎么填报$",
            r"怎么.{0,4}$", r"多少个$", r"多少$", r"哪些$",
            r"名单$", r"清单$", r"内容$", r"情况$", r"信息$",
        ]
        for p in patterns:
            q = re.sub(p, "", q)
        return q.strip() or question

    async def _run_tool(
        self,
        tool_name: str,
        question: str,
        tool_args: dict[str, Any],
        *,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any] | None:
        tool = self.tools.get(tool_name)
        if tool is None:
            return None
        if tool_name == "map_route" and history:
            return await tool.run(question, history=history, **tool_args)
        return await tool.run(question, **tool_args)

    async def _gather_evidence(
        self,
        question: str,
        plan: RoutePlan,
        rag_query: str,
        *,
        history: list[dict[str, str]] | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """子 Agent 取证 + Supervisor 裁决优先级并过滤证据。"""
        primary = plan.primary
        evidence: dict[str, Any] = {
            "question": question,
            "route_mode": plan.mode,
            "collab_reason": plan.collab_reason,
            "intent": primary.model_dump(),
            "intents": [i.model_dump() for i in plan.intents],
        }

        tool_intents = [i for i in plan.intents if i.path in ("tool", "hybrid") and i.tool]

        print(
            f"[Agent] 模式={plan.mode} 原因={plan.collab_reason or '-'} "
            f"子Agent={[i.tool for i in tool_intents]}"
        )

        # --- 阶段1：工具类子 Agent 取证 ---
        if tool_intents:
            if plan.mode == "collab":
                tasks = [
                    self._run_tool(i.tool, question, i.tool_args, history=history)
                    for i in tool_intents
                    if i.tool
                ]
                results = await asyncio.gather(*tasks)
                tool_results = [r for r in results if r is not None]
            else:
                intent = tool_intents[0]
                assert intent.tool
                tool_result = await self._run_tool(
                    intent.tool, question, intent.tool_args, history=history
                )
                tool_results = [tool_result] if tool_result else []
                if intent.tool == "academic_search" and tool_result:
                    query_used = tool_result.get("query_used", {})
                    if query_used:
                        evidence["llm_query_optimization"] = query_used

            evidence["tool_results"] = tool_results
            if tool_results:
                evidence["tool_result"] = tool_results[0]
            for tr in tool_results:
                print(f"[Agent] 子Agent {tr.get('tool')} 返回: {len(tr.get('items', []))} 条")

        # --- 阶段2：Supervisor 决定是否调用 RAG / 文档 Agent ---
        fetch_rag = self.supervisor.should_fetch_rag(evidence, plan)
        fetch_doc = self.supervisor.should_fetch_doc(evidence, plan)
        print(f"[Supervisor] 是否调用RAG={fetch_rag} 文档库={fetch_doc}")

        if fetch_rag:
            evidence["rag_hits"] = await self.retriever.search(rag_query)
            print(f"[Agent] RAG Agent 命中: {len(evidence.get('rag_hits', []))} 条")

        if fetch_doc:
            evidence["doc_hits"] = await self.retriever.search_documents(
                rag_query, user_id=user_id
            )
            if evidence.get("doc_hits"):
                print(f"[Agent] 文档 Agent 命中: {len(evidence['doc_hits'])} 条")

        # --- 阶段3：Supervisor 裁决优先级并过滤证据 ---
        decision = self.supervisor.decide(evidence, plan)
        filtered = self.supervisor.apply(evidence, decision)
        print(
            f"[Supervisor] 优先级={decision.priority} 原因={decision.reason} "
            f"用RAG={decision.use_rag} 用文档={decision.use_doc}"
        )
        return filtered

    async def handle(
        self,
        question: str,
        *,
        session_id: str | None = None,
        user_role: str = "student",
        history: list[dict[str, str]] | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        plan = self.router.route(question)
        rag_query = self._clean_query(question)
        print(f"[Agent] RAG 查询: '{rag_query}' (原始: '{question}')")

        if plan.primary.path == "fallback":
            return self.fallback.no_evidence(question)

        evidence = await self._gather_evidence(
            question, plan, rag_query, history=history, user_id=user_id
        )
        result = await self.answer_generator.generate(question, evidence, history=history)

        if not result.get("sources") and self.fallback.enabled:
            return self.fallback.no_evidence(question)

        result["route_mode"] = plan.mode
        result["evidence_priority"] = evidence.get("evidence_priority")
        result["supervisor_reason"] = evidence.get("supervisor_reason")
        if plan.mode == "collab":
            result["agents_used"] = evidence.get("supervisor_agents") or [
                i.intent_label for i in plan.intents if i.intent_label
            ]
        return result

    async def handle_stream(
        self,
        question: str,
        *,
        session_id: str | None = None,
        user_role: str = "student",
        history: list[dict[str, str]] | None = None,
        user_id: int | None = None,
    ):
        import json

        plan = self.router.route(question)
        rag_query = self._clean_query(question)

        if plan.primary.path == "fallback":
            fb = self.fallback.no_evidence(question)
            meta = {
                "type": "meta",
                "confidence": "low",
                "sources": fb.get("sources", []),
                "attachments": [],
                "tools_used": [],
                "fallback": True,
            }
            yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
            yield f'data: {json.dumps({"type": "token", "content": fb.get("answer", "")}, ensure_ascii=False)}\n\n'
            yield f'data: {json.dumps({"type": "done"}, ensure_ascii=False)}\n\n'
            return

        evidence = await self._gather_evidence(
            question, plan, rag_query, history=history, user_id=user_id
        )

        # Supervisor 裁决事件
        supervisor_evt = {
            "type": "supervisor",
            "priority": evidence.get("evidence_priority"),
            "reason": evidence.get("supervisor_reason"),
            "agents": evidence.get("supervisor_agents", []),
        }
        yield f"data: {json.dumps(supervisor_evt, ensure_ascii=False)}\n\n"

        if plan.mode == "collab":
            progress = {
                "type": "agents",
                "mode": "collab",
                "reason": plan.collab_reason,
                "agents": [i.intent_label for i in plan.intents if i.intent_label],
            }
            yield f"data: {json.dumps(progress, ensure_ascii=False)}\n\n"

        async for chunk in self.answer_generator.generate_stream(question, evidence, history=history):
            yield chunk
