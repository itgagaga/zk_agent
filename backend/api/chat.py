"""聊天问答 API。

接收用户自然语言问题，调用 Agent 主控生成带来源的回答。
支持流式 SSE 输出。
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.agents.controller import AgentController

router = APIRouter()


class ChatRequest(BaseModel):
    """聊天请求。"""

    question: str = Field(..., description="用户问题")
    session_id: str | None = Field(default=None, description="会话 ID，用于多轮对话")
    user_role: Literal["student", "teacher", "graduate", "applicant", "visitor", "admin"] = Field(
        default="student", description="用户角色，用于个性化推荐"
    )
    history: list[dict] = Field(default_factory=list, description="历史对话，用于多轮上下文")


class SourceItem(BaseModel):
    """来源引用项。"""

    title: str
    department: str | None = None
    url: str
    publish_date: str | None = None
    snippet: str | None = None


class AttachmentItem(BaseModel):
    """附件信息。"""

    name: str
    file_type: str | None = None
    source_page_url: str | None = None
    file_url: str | None = None


class ChatResponse(BaseModel):
    """聊天响应。"""

    answer: str
    confidence: Literal["high", "medium", "low"]
    sources: list[SourceItem] = Field(default_factory=list)
    attachments: list[AttachmentItem] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    fallback: bool = False
    session_id: str | None = None
    llm_query_optimization: dict | None = Field(
        default=None, description="LLM 关键词优化结果（学术搜索专用）"
    )


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """主问答接口（非流式）。

    接收用户问题，由 Agent 主控模块判断意图、选择工具、
    调用 RAG 或结构化工具，最终生成带来源的回答。
    """
    controller = AgentController()
    result = await controller.handle(req.question, session_id=req.session_id, user_role=req.user_role, history=req.history)
    return ChatResponse(**result)


@router.post("/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """流式问答接口（SSE）。

    返回 text/event-stream，事件序列：
      1. meta  — 来源/附件/工具/置信度
      2. token — 逐 token 返回回答文本
      3. done  — 完成
    """
    controller = AgentController()

    async def event_generator():
        async for chunk in controller.handle_stream(
            req.question, session_id=req.session_id, user_role=req.user_role, history=req.history
        ):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
