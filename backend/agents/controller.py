"""Agent 主控模块。

负责统一接收用户问题，调用 router 判断意图，
分发到 RAG / 智能文档 / 结构化工具，
最终由 answer_generator 生成带来源的回答。
"""
from __future__ import annotations

import re
from typing import Any

from backend.agents.answer_generator import AnswerGenerator
from backend.agents.fallback import FallbackHandler
from backend.agents.router import IntentResult, QuestionRouter
from backend.rag.retriever import RAGRetriever
from backend.tools.contact_tool import ContactTool
from backend.tools.download_tool import DownloadTool
from backend.tools.major_tool import MajorTool
from backend.tools.service_link_tool import ServiceLinkTool


class AgentController:
    """Agent 主控。

    工作流：
        用户问题 → 意图识别 → 选择路径 → 执行检索/工具 → 整合证据 → 生成回答 → 兜底检查
    """

    def __init__(self) -> None:
        self.router = QuestionRouter()
        self.retriever = RAGRetriever()
        self.answer_generator = AnswerGenerator()
        self.fallback = FallbackHandler()
        # 结构化工具
        self.tools: dict[str, Any] = {
            "major_search": MajorTool(),
            "download_search": DownloadTool(),
            "contact_search": ContactTool(),
            "service_link_search": ServiceLinkTool(),
        }

    @staticmethod
    def _clean_query(question: str) -> str:
        """清洗查询文本，去掉常见问句模板词，提高 RAG 检索准确率。

        bge-small-zh 对长文本语义匹配有限，
        "主要讲了什么"等尾部模板词会严重干扰向量匹配。
        """
        q = re.sub(r"[？?]+$", "", question)
        # 按优先级去掉尾部问句模板
        patterns = [
            r"主要讲了什么内容$",
            r"主要讲了什么$",
            r"主要讲了哪些$",
            r"讲了什么$",
            r"说了什么$",
            r"主要介绍什么$",
            r"介绍.{0,2}$",
            r"是什么$",
            r"有哪些$",
            r"有什么$",
            r"是哪些$",
            r"在哪里$",
            r"在哪$",
            r"怎么申请$",
            r"怎么办理$",
            r"怎么填报$",
            r"怎么.{0,4}$",
            r"多少个$",
            r"多少$",
            r"哪些$",
            r"名单$",
            r"清单$",
            r"内容$",
            r"情况$",
            r"信息$",
        ]
        for p in patterns:
            q = re.sub(p, "", q)
        return q.strip() or question

    async def handle(
        self,
        question: str,
        *,
        session_id: str | None = None,
        user_role: str = "student",
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """处理用户问题，返回完整响应字典。"""
        # 1. 意图识别
        intent: IntentResult = self.router.route(question)
        # 清洗查询，用于 RAG 检索（工具仍用原始问题做关键词匹配）
        rag_query = self._clean_query(question)

        # 2. 执行对应路径
        evidence: dict[str, Any] = {"question": question, "intent": intent.model_dump()}
        print(f"[Agent] 路由: path={intent.path} tool={intent.tool} label={intent.intent_label}")
        print(f"[Agent] RAG 查询: '{rag_query}' (原始: '{question}')")

        if intent.path == "general_rag":
            evidence["rag_hits"] = await self.retriever.search(rag_query)
            print(f"[Agent] RAG 命中: {len(evidence.get('rag_hits', []))} 条")
        elif intent.path == "document_rag":
            # 同时查通用知识库和文档知识库（第一阶段资料都在 campus 集合）
            evidence["rag_hits"] = await self.retriever.search(rag_query)
            evidence["doc_hits"] = await self.retriever.search_documents(rag_query)
            print(f"[Agent] RAG 命中: {len(evidence.get('rag_hits', []))} 条, 文档命中: {len(evidence.get('doc_hits', []))} 条")
        elif intent.path == "tool" and intent.tool:
            # 工具查询同时也做 RAG 检索，补充上下文
            evidence["rag_hits"] = await self.retriever.search(rag_query)
            print(f"[Agent] RAG 命中: {len(evidence.get('rag_hits', []))} 条")
            tool = self.tools.get(intent.tool)
            if tool is not None:
                evidence["tool_result"] = await tool.run(question, **intent.tool_args)
                item_count = len(evidence.get("tool_result", {}).get("items", []))
                print(f"[Agent] 工具 {intent.tool} 返回: {item_count} 条")
            else:
                evidence["rag_hits"] = await self.retriever.search(rag_query)
        elif intent.path == "hybrid":
            evidence["rag_hits"] = await self.retriever.search(rag_query)
            if intent.tool:
                tool = self.tools.get(intent.tool)
                if tool is not None:
                    evidence["tool_result"] = await tool.run(question, **intent.tool_args)
        elif intent.path == "fallback":
            return self.fallback.no_evidence(question)

        # 永久文档库始终参与检索（RAG 相似度阈值自动过滤无关内容）
        if "doc_hits" not in evidence:
            evidence["doc_hits"] = await self.retriever.search_documents(rag_query)
            if evidence["doc_hits"]:
                print(f"[Agent] 文档库命中: {len(evidence['doc_hits'])} 条")

        # 3. 生成回答
        result = await self.answer_generator.generate(question, evidence, history=history)

        # 4. 兜底检查
        if not result.get("sources") and self.fallback.enabled:
            return self.fallback.no_evidence(question)

        return result

    async def handle_stream(
        self,
        question: str,
        *,
        session_id: str | None = None,
        user_role: str = "student",
        history: list[dict[str, str]] | None = None,
    ):
        """流式处理用户问题，yield SSE 格式字符串。"""
        import json

        # 1. 意图识别
        intent: IntentResult = self.router.route(question)
        rag_query = self._clean_query(question)

        # 2. 执行对应路径
        evidence: dict[str, Any] = {"question": question, "intent": intent.model_dump()}
        print(f"[Agent-Stream] 路由: path={intent.path} tool={intent.tool}")
        print(f"[Agent-Stream] RAG 查询: '{rag_query}'")

        if intent.path == "general_rag":
            evidence["rag_hits"] = await self.retriever.search(rag_query)
        elif intent.path == "document_rag":
            evidence["rag_hits"] = await self.retriever.search(rag_query)
            evidence["doc_hits"] = await self.retriever.search_documents(rag_query)
        elif intent.path == "tool" and intent.tool:
            evidence["rag_hits"] = await self.retriever.search(rag_query)
            tool = self.tools.get(intent.tool)
            if tool is not None:
                evidence["tool_result"] = await tool.run(question, **intent.tool_args)
            else:
                evidence["rag_hits"] = await self.retriever.search(rag_query)
        elif intent.path == "hybrid":
            evidence["rag_hits"] = await self.retriever.search(rag_query)
            if intent.tool:
                tool = self.tools.get(intent.tool)
                if tool is not None:
                    evidence["tool_result"] = await tool.run(question, **intent.tool_args)
        elif intent.path == "fallback":
            # 兜底也走流式
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

        # 永久文档库始终参与检索（RAG 相似度阈值自动过滤无关内容）
        if "doc_hits" not in evidence:
            evidence["doc_hits"] = await self.retriever.search_documents(rag_query)
            if evidence["doc_hits"]:
                print(f"[Agent-Stream] 文档库命中: {len(evidence['doc_hits'])} 条")

        print(f"[Agent-Stream] RAG 命中: {len(evidence.get('rag_hits', []))} 条")

        # 3. 流式生成
        async for chunk in self.answer_generator.generate_stream(question, evidence, history=history):
            yield chunk
