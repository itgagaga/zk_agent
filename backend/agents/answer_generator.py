"""答案生成模块。

整合 RAG 检索结果、工具结果和来源信息，调用大模型生成最终回答。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncGenerator
from urllib.parse import urldefrag, urlsplit, urlunsplit

from backend.config import settings
from backend.rag.prompt_templates import build_qa_prompt
from backend.rag.retriever import RAGRetriever
from backend.utils.deepseek import create_deepseek_chat
from backend.utils.llm_content import extract_text_content


logger = logging.getLogger(__name__)


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
            self.llm = create_deepseek_chat(
                model=settings.deepseek_model,
                temperature=0.3,
                max_tokens=2000,
            )
        except Exception as e:
            print(f"[AnswerGenerator] LLM 初始化失败: {e}")

    def _get_tool_results(self, evidence: dict[str, Any]) -> list[dict[str, Any]]:
        """从 evidence 中提取工具结果列表（兼容单/多工具）。"""
        tool_results = evidence.get("tool_results") or []
        if not tool_results and evidence.get("tool_result"):
            tool_results = [evidence["tool_result"]]
        return tool_results

    @staticmethod
    def _display_source_identity(source: dict[str, Any]) -> tuple[str, ...] | None:
        """生成展示层来源标识，不参与检索、证据准备或答案生成。"""
        doc_id = str(source.get("doc_id") or "").strip()
        if doc_id:
            return ("doc_id", doc_id)

        url = str(source.get("url") or "").strip()
        if url:
            fragmentless_url = urldefrag(url)[0]
            parsed = urlsplit(fragmentless_url)
            normalized_url = urlunsplit(
                (
                    parsed.scheme.lower(),
                    parsed.netloc.lower(),
                    parsed.path.rstrip("/") or ("/" if parsed.netloc else ""),
                    parsed.query,
                    "",
                )
            )
            return ("url", normalized_url)

        title = "".join(str(source.get("title") or "").split()).lower()
        department = "".join(str(source.get("department") or "").split()).lower()
        if title:
            return ("title", title, department)
        return None

    @classmethod
    def _deduplicate_display_sources(
        cls,
        sources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """仅对响应中的展示来源去重，并保留排序最靠前的位置。"""
        display_sources: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for source in sources:
            identity = cls._display_source_identity(source)
            if identity is not None and identity in seen:
                continue
            if identity is not None:
                seen.add(identity)
            display_sources.append(source)
        return display_sources

    def _prepare_evidence(self, evidence: dict[str, Any]) -> tuple[list[dict], list[dict], list[str], list[dict], list[dict]]:
        """从 evidence 中提取来源、附件、工具名、tool_results 和用户上传来源。"""
        sources: list[dict[str, Any]] = []
        user_sources: list[dict[str, Any]] = []
        attachments: list[dict[str, Any]] = []
        tools_used: list[str] = []
        tool_results = self._get_tool_results(evidence)

        def _classify(hit: dict[str, Any], from_doc_library: bool = False) -> None:
            meta = hit.get("metadata", {}) or {}
            entry = {
                "title": hit.get("title", ""),
                "department": hit.get("department"),
                "url": hit.get("url", ""),
                "publish_date": hit.get("publish_date"),
                "snippet": hit.get("snippet", ""),
                "evidence_id": hit.get("evidence_id") or hit.get("chunk_id"),
                "retriever": hit.get("retriever"),
                "score": hit.get("score"),
                "chunk_id": hit.get("chunk_id"),
                "doc_id": hit.get("doc_id") or meta.get("doc_id"),
            }
            if from_doc_library or meta.get("user_id") is not None:
                user_sources.append(entry)
            else:
                sources.append(entry)

        for hit in evidence.get("rag_hits", []) or []:
            _classify(hit)

        for hit in evidence.get("doc_hits", []) or []:
            _classify(hit, from_doc_library=True)

        for tool_result in tool_results:
            tool_name = tool_result.get("tool", "")
            if tool_name and tool_name not in tools_used:
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
                        "snippet": (
                            item.get("snippet")
                            or item.get("summary")
                            or item.get("service_scope")
                            or item.get("description", "")
                        ),
                        "evidence_id": item.get("evidence_id"),
                        "retriever": tool_name,
                        "score": item.get("match_score") or item.get("score"),
                    }
                )

        return sources, attachments, tools_used, tool_results, user_sources

    def _confidence(self, sources: list[dict]) -> str:
        """根据来源数量判断置信度。"""
        if not sources:
            return "low"
        if len(sources) == 1:
            return "medium"
        return "high"

    async def generate(self, question: str, evidence: dict[str, Any], history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """根据已融合、已门控的证据生成回答。"""
        sources, attachments, tools_used, tool_results, user_sources = self._prepare_evidence(evidence)
        mode = evidence.get("evidence_mode") or evidence.get("evidence_priority") or "rag"
        legacy_priority = evidence.get("evidence_priority", mode)
        prompt = build_qa_prompt(
            question,
            sources=sources,
            tool_results=tool_results,
            history=history,
            user_sources=user_sources,
            evidence_mode=mode,
            evidence_priority=legacy_priority,
        )
        answer_text = await self._call_llm(prompt)
        confidence = self._confidence(sources + user_sources)
        display_sources = self._deduplicate_display_sources(sources + user_sources)

        result = {
            "answer": answer_text,
            "confidence": confidence,
            "sources": display_sources,
            "attachments": attachments,
            "tools_used": tools_used,
            "fallback": False,
            "session_id": None,
            "route_mode": evidence.get("route_mode", "fast"),
            "evidence_mode": mode,
            # Deprecated compatibility field; never used to select evidence.
            "evidence_priority": legacy_priority,
            "supervisor_reason": evidence.get("supervisor_reason"),
        }
        llm_query_opt = evidence.get("llm_query_optimization")
        if llm_query_opt:
            result["llm_query_optimization"] = llm_query_opt
        if evidence.get("retrieval_summary"):
            result["retrieval_summary"] = evidence["retrieval_summary"]
        return result

    async def generate_stream(self, question: str, evidence: dict[str, Any], history: list[dict[str, str]] | None = None) -> AsyncGenerator[str, None]:
        """流式生成回答，逐条 yield SSE 格式字符串。"""
        started_at = time.perf_counter()
        retrieval_summary = evidence.get("retrieval_summary") or {}
        trace_id = retrieval_summary.get("trace_id", "-")
        logger.info("answer_stream_started trace_id=%s", trace_id)
        sources, attachments, tools_used, tool_results, user_sources = self._prepare_evidence(evidence)
        confidence = self._confidence(sources + user_sources)
        display_sources = self._deduplicate_display_sources(sources + user_sources)

        meta = {
            "type": "meta",
            "confidence": confidence,
            "sources": display_sources,
            "attachments": attachments,
            "tools_used": tools_used,
            "fallback": False,
            "route_mode": evidence.get("route_mode", "fast"),
            "evidence_mode": evidence.get("evidence_mode") or evidence.get("evidence_priority") or "rag",
            # Deprecated compatibility field for older clients.
            "evidence_priority": evidence.get("evidence_priority", "rag"),
            "supervisor_reason": evidence.get("supervisor_reason"),
        }
        if evidence.get("retrieval_summary"):
            meta["retrieval_summary"] = evidence["retrieval_summary"]
        llm_query_opt = evidence.get("llm_query_optimization")
        if llm_query_opt:
            meta["llm_query_optimization"] = llm_query_opt
        yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"

        prompt = build_qa_prompt(
            question,
            sources=sources,
            tool_results=tool_results,
            history=history,
            user_sources=user_sources,
            evidence_mode=evidence.get("evidence_mode") or evidence.get("evidence_priority") or "rag",
            evidence_priority=evidence.get("evidence_priority"),
        )
        emitted_text = False
        first_token_at: float | None = None
        reasoning_chunks = 0
        reasoning_chars = 0
        finish_reason: str | None = None
        usage_present = False
        stream_status = "completed"
        if self.llm is None:
            emitted_text = True
            stream_status = "llm_uninitialized"
            yield f'data: {json.dumps({"type": "token", "content": "(LLM 未初始化，请检查 DEEPSEEK_API_KEY 配置)"}, ensure_ascii=False)}\n\n'
        else:
            try:
                async for chunk in self.llm.astream(prompt):
                    response_metadata = getattr(chunk, "response_metadata", {}) or {}
                    generation_info = getattr(chunk, "generation_info", {}) or {}
                    finish_reason = (
                        response_metadata.get("finish_reason")
                        or generation_info.get("finish_reason")
                        or finish_reason
                    )
                    usage_present = usage_present or bool(
                        response_metadata.get("usage")
                        or response_metadata.get("token_usage")
                        or getattr(chunk, "usage_metadata", None)
                    )
                    additional_kwargs = getattr(chunk, "additional_kwargs", {}) or {}
                    reasoning = additional_kwargs.get("reasoning_content")
                    if reasoning:
                        reasoning_chunks += 1
                        reasoning_chars += len(str(reasoning))
                    token = extract_text_content(chunk)
                    if token:
                        emitted_text = True
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                            logger.info(
                                "answer_stream_first_token trace_id=%s duration_ms=%.1f",
                                trace_id,
                                (first_token_at - started_at) * 1000,
                            )
                        yield f'data: {json.dumps({"type": "token", "content": token}, ensure_ascii=False)}\n\n'
            except Exception as e:
                stream_status = "error"
                logger.warning(
                    "answer_stream_error trace_id=%s error_type=%s",
                    trace_id,
                    type(e).__name__,
                )
                if not emitted_text:
                    emitted_text = True
                    yield f'data: {json.dumps({"type": "token", "content": "(LLM 调用失败，请稍后重试)"}, ensure_ascii=False)}\n\n'

        # 某些兼容接口会正常结束，但整个流只有空 content/reasoning 块。
        # 不能只发 done，否则前端会留下“仅有来源引用”的空回答。
        if not emitted_text:
            stream_status = "empty"
            logger.warning(
                "answer_stream_empty trace_id=%s finish_reason=%s reasoning_chunks=%s "
                "reasoning_chars=%s duration_ms=%.1f",
                trace_id,
                finish_reason or "unknown",
                reasoning_chunks,
                reasoning_chars,
                (time.perf_counter() - started_at) * 1000,
            )
            yield f'data: {json.dumps({"type": "token", "content": "模型未返回有效回答，请重试。"}, ensure_ascii=False)}\n\n'

        logger.info(
            "answer_stream_completed trace_id=%s status=%s finish_reason=%s "
            "reasoning_chunks=%s reasoning_chars=%s usage_present=%s "
            "first_token_ms=%s duration_ms=%.1f",
            trace_id,
            stream_status,
            finish_reason or "unknown",
            reasoning_chunks,
            reasoning_chars,
            usage_present,
            f"{(first_token_at - started_at) * 1000:.1f}" if first_token_at else "-",
            (time.perf_counter() - started_at) * 1000,
        )

        # 3. 发 done
        yield f'data: {json.dumps({"type": "done"}, ensure_ascii=False)}\n\n'

    async def _call_llm(self, prompt: str) -> str:
        """调用 DeepSeek 大模型（非流式）。"""
        if self.llm is None:
            return "(LLM 未初始化，请检查 DEEPSEEK_API_KEY 配置)"
        try:
            response = await self.llm.ainvoke(prompt)
            text = extract_text_content(response)
            return text or "模型未返回有效回答，请重试。"
        except Exception as e:
            return f"(LLM 调用失败: {e})"
