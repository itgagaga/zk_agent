"""用户注册 / 登录 / 当前用户信息 API。"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.auth.deps import get_current_user
from backend.auth.security import create_access_token, hash_password, verify_password
from backend.database.models import User
from backend.database.session import get_db

router = APIRouter()

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_\u4e00-\u9fff]{2,32}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    """注册请求。"""

    username: str = Field(..., min_length=2, max_length=32, description="用户名")
    password: str = Field(..., min_length=6, max_length=64, description="密码")
    email: str | None = Field(default=None, max_length=128, description="邮箱（可选）")
    display_name: str | None = Field(
        default=None, max_length=64, description="显示名称（可选）"
    )
    role: str = Field(default="student", description="角色：student / teacher")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if not _USERNAME_RE.match(v):
            raise ValueError("用户名仅支持中英文、数字、下划线，长度 2–32")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("邮箱格式不正确")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"student", "teacher"}
        v = (v or "student").strip().lower()
        if v not in allowed:
            raise ValueError("角色仅支持 student 或 teacher")
        return v

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class LoginRequest(BaseModel):
    """登录请求（可用用户名或邮箱）。"""

    username: str = Field(..., min_length=1, max_length=128, description="用户名或邮箱")
    password: str = Field(..., min_length=1, max_length=64, description="密码")


class UserOut(BaseModel):
    """对外用户信息（不含密码）。"""

    id: int
    username: str
    email: str | None = None
    display_name: str | None = None
    role: str = "student"
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """登录/注册成功响应。"""

    access_token: str
    token_type: str = "bearer"
    user: UserOut


def _to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name or user.username,
        role=user.role or "student",
        created_at=user.created_at,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """注册新用户，成功后直接返回 token。"""
    exists = (
        db.query(User)
        .filter(
            or_(
                User.username == req.username,
                *( [User.email == req.email] if req.email else [] ),
            )
        )
        .first()
    )
    if exists:
        if exists.username == req.username:
            raise HTTPException(status_code=400, detail="用户名已被注册")
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
        display_name=req.display_name or req.username,
        role=req.role,
        is_active=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        user.id,
        extra={"username": user.username, "role": user.role or "student"},
    )
    return AuthResponse(access_token=token, user=_to_user_out(user))


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """用户名或邮箱 + 密码登录。"""
    account = req.username.strip()
    user = (
        db.query(User)
        .filter(or_(User.username == account, User.email == account.lower()))
        .first()
    )
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已停用")

    token = create_access_token(
        user.id,
        extra={"username": user.username, "role": user.role or "student"},
    )
    return AuthResponse(access_token=token, user=_to_user_out(user))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """获取当前登录用户信息。"""
    return _to_user_out(current_user)
