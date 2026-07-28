"""聊天问答 API。

接收用户自然语言问题，调用 Agent 主控生成带来源的回答。
支持流式 SSE 输出；登录用户可持久化会话与消息。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.agents.controller import AgentController
from backend.auth.deps import get_current_user, get_current_user_optional
from backend.database.models import ChatMessage, ChatSession, User
from backend.database.session import get_db

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


class SessionCreate(BaseModel):
    title: str = Field(default="新对话", max_length=256)


class SessionOut(BaseModel):
    id: int
    title: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class MessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = ""
    meta: dict[str, Any] | None = None


class MessagesBatchIn(BaseModel):
    messages: list[MessageIn]


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    meta: dict[str, Any] | None = None
    created_at: datetime | None = None


def _parse_meta(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _own_session(db: Session, session_id: int, user_id: int) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: User | None = Depends(get_current_user_optional),
) -> ChatResponse:
    """主问答接口（非流式）。"""
    controller = AgentController()
    role = (current_user.role if current_user else None) or req.user_role
    result = await controller.handle(
        req.question,
        session_id=req.session_id,
        user_role=role,
        history=req.history,
        user_id=current_user.id if current_user else None,
    )
    return ChatResponse(**result)


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    current_user: User | None = Depends(get_current_user_optional),
) -> StreamingResponse:
    """流式问答接口（SSE）。"""
    controller = AgentController()
    role = (current_user.role if current_user else None) or req.user_role
    user_id = current_user.id if current_user else None

    async def event_generator():
        async for chunk in controller.handle_stream(
            req.question,
            session_id=req.session_id,
            user_role=role,
            history=req.history,
            user_id=user_id,
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


# ---------- 登录用户：会话 / 消息持久化 ----------

@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SessionOut]:
    rows = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return [SessionOut.model_validate(r) for r in rows]


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    req: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionOut:
    now = datetime.utcnow()
    row = ChatSession(
        user_id=current_user.id,
        title=(req.title or "新对话").strip() or "新对话",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return SessionOut.model_validate(row)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = _own_session(db, session_id, current_user.id)
    db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete()
    db.delete(session)
    db.commit()
    return {"ok": True, "id": session_id}


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    _own_session(db, session_id, current_user.id)
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.asc())
        .all()
    )
    return [
        MessageOut(
            id=r.id,
            role=r.role,
            content=r.content or "",
            meta=_parse_meta(r.meta),
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def append_messages(
    session_id: int,
    req: MessagesBatchIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    session = _own_session(db, session_id, current_user.id)
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages 不能为空")

    now = datetime.utcnow()
    created: list[ChatMessage] = []
    for item in req.messages:
        row = ChatMessage(
            session_id=session.id,
            role=item.role,
            content=item.content or "",
            meta=json.dumps(item.meta, ensure_ascii=False) if item.meta else None,
            created_at=now,
        )
        db.add(row)
        created.append(row)

    # 用首条用户消息更新标题
    if (session.title or "新对话") in ("新对话", "") and req.messages:
        first_user = next((m for m in req.messages if m.role == "user" and m.content), None)
        if first_user:
            session.title = first_user.content.strip()[:40]

    session.updated_at = now
    db.commit()
    for row in created:
        db.refresh(row)

    return [
        MessageOut(
            id=r.id,
            role=r.role,
            content=r.content or "",
            meta=_parse_meta(r.meta),
            created_at=r.created_at,
        )
        for r in created
    ]


@router.delete("/sessions/{session_id}/messages")
async def clear_messages(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = _own_session(db, session_id, current_user.id)
    db.query(ChatMessage).filter(ChatMessage.session_id == session.id).delete()
    session.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "id": session_id}
