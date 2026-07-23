"""答案生成模块。

整合 RAG 检索结果、工具结果和来源信息，调用大模型生成最终回答。
"""
from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from backend.config import settings
from backend.rag.prompt_templates import build_qa_prompt
from backend.rag.retriever import RAGRetriever


class AnswerGenerator:
    """答案生成器。

    输入：用户问题 + 证据（RAG 命中、工具结果、文档片段）
    输出：包含 answer / confidence / sources / attachments / tools_used 的字典
    """

    def __init__(self) -> None:
        self.retriever = RAGRetriever()
        self.llm: Any = None
        self._init_llm()

    def _init_llm(self) -> None:
        """初始化 DeepSeek LLM 客户端。"""
        if not settings.deepseek_api_key:
            return
        try:
            from langchain_deepseek import ChatDeepSeek

            self.llm = ChatDeepSeek(
                model=settings.deepseek_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                temperature=0.3,
                max_tokens=2000,
            )
        except Exception as e:
            print(f"[AnswerGenerator] LLM 初始化失败: {e}")

    def _prepare_evidence(self, evidence: dict[str, Any]) -> tuple[list[dict], list[dict], list[str], Any, list[dict]]:
        """从 evidence 中提取来源、附件、工具名、tool_result 和用户上传来源。

        返回：(official_sources, attachments, tools_used, tool_result, user_sources)
        user_sources 单独分离，department=="用户上传" 的来源归入此列表。
        """
        sources: list[dict[str, Any]] = []
        user_sources: list[dict[str, Any]] = []
        attachments: list[dict[str, Any]] = []
        tools_used: list[str] = []

        def _classify(hit: dict[str, Any], from_doc_library: bool = False) -> None:
            entry = {
                "title": hit.get("title", ""),
                "department": hit.get("department"),
                "url": hit.get("url", ""),
                "publish_date": hit.get("publish_date"),
                "snippet": hit.get("snippet", ""),
            }
            # 来自文档库（zhku_documents 集合）的命中视为"上传文档"
            meta = hit.get("metadata", {}) or {}
            if from_doc_library or meta.get("doc_id"):
                user_sources.append(entry)
            else:
                sources.append(entry)

        for hit in evidence.get("rag_hits", []) or []:
            _classify(hit)

        for hit in evidence.get("doc_hits", []) or []:
            _classify(hit, from_doc_library=True)

        tool_result = evidence.get("tool_result")
        if tool_result:
            tool_name = evidence.get("intent", {}).get("tool", "")
            if tool_name:
                tools_used.append(tool_name)
            for item in tool_result.get("items", []) or []:
                if item.get("file_url") or item.get("source_page_url"):
                    attachments.append(
                        {
                            "name": item.get("title") or item.get("name", ""),
                            "file_type": item.get("file_type"),
                            "source_page_url": item.get("source_page_url"),
                            "file_url": item.get("file_url"),
                        }
                    )
                sources.append(
                    {
                        "title": item.get("title") or item.get("name", ""),
                        "department": item.get("department"),
                        "url": item.get("source_page_url") or item.get("url", ""),
                        "publish_date": item.get("publish_date"),
                        "snippet": item.get("service_scope") or item.get("description", ""),
                    }
                )

        return sources, attachments, tools_used, tool_result, user_sources

    def _confidence(self, sources: list[dict]) -> str:
        """根据来源数量判断置信度。"""
        if not sources:
            return "low"
        if len(sources) == 1:
            return "medium"
        return "high"

    async def generate(self, question: str, evidence: dict[str, Any], history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """根据证据生成回答。"""
        sources, attachments, tools_used, tool_result, user_sources = self._prepare_evidence(evidence)
        prompt = build_qa_prompt(question, sources=sources, tool_result=tool_result, history=history, user_sources=user_sources)
        answer_text = await self._call_llm(prompt)
        confidence = self._confidence(sources + user_sources)

        return {
            "answer": answer_text,
            "confidence": confidence,
            "sources": sources + user_sources,
            "attachments": attachments,
            "tools_used": tools_used,
            "fallback": False,
            "session_id": None,
        }

    async def generate_stream(self, question: str, evidence: dict[str, Any], history: list[dict[str, str]] | None = None) -> AsyncGenerator[str, None]:
        """流式生成回答，逐条 yield SSE 格式字符串。

        事件序列：
          1. meta  — 来源/附件/工具/置信度
          2. token — 逐 token 返回回答文本
          3. done  — 完成
        """
        sources, attachments, tools_used, tool_result, user_sources = self._prepare_evidence(evidence)
        confidence = self._confidence(sources + user_sources)

        # 1. 先发 meta
        meta = {
            "type": "meta",
            "confidence": confidence,
            "sources": sources + user_sources,
            "attachments": attachments,
            "tools_used": tools_used,
            "fallback": False,
        }
        yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"

        # 2. 流式输出 LLM token
        prompt = build_qa_prompt(question, sources=sources, tool_result=tool_result, history=history, user_sources=user_sources)
        if self.llm is None:
            yield f'data: {json.dumps({"type": "token", "content": "(LLM 未初始化，请检查 DEEPSEEK_API_KEY 配置)"}, ensure_ascii=False)}\n\n'
        else:
            try:
                async for chunk in self.llm.astream(prompt):
                    token = chunk.content
                    if token:
                        yield f'data: {json.dumps({"type": "token", "content": token}, ensure_ascii=False)}\n\n'
            except Exception as e:
                yield f'data: {json.dumps({"type": "token", "content": f"(LLM 调用失败: {e})"}, ensure_ascii=False)}\n\n'

        # 3. 发 done
        yield f'data: {json.dumps({"type": "done"}, ensure_ascii=False)}\n\n'

    async def _call_llm(self, prompt: str) -> str:
        """调用 DeepSeek 大模型（非流式）。"""
        if self.llm is None:
            return "(LLM 未初始化，请检查 DEEPSEEK_API_KEY 配置)"
        try:
            response = await self.llm.ainvoke(prompt)
            return response.content
        except Exception as e:
            return f"(LLM 调用失败: {e})"
