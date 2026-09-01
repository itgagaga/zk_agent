"""统一创建 DeepSeek Chat 客户端。

DeepSeek V4 默认开启思考模式。聊天主链路默认关闭思考，避免有限的
``max_tokens`` 被 reasoning_content 消耗完而没有可展示的 content。
"""
from __future__ import annotations

from typing import Any

from backend.config import settings


def create_deepseek_chat(
    *,
    model: str,
    max_tokens: int,
    temperature: float | None = None,
) -> Any:
    """按项目配置创建 ChatDeepSeek，统一超时、重试和思考模式。"""
    from langchain_deepseek import ChatDeepSeek

    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": settings.deepseek_api_key,
        "base_url": settings.deepseek_base_url,
        "max_tokens": max_tokens,
        "timeout": settings.deepseek_timeout_seconds,
        "max_retries": settings.deepseek_max_retries,
        "extra_body": {"thinking": {"type": settings.deepseek_thinking_mode}},
    }
    if temperature is not None and settings.deepseek_thinking_mode == "disabled":
        kwargs["temperature"] = temperature
    if settings.deepseek_thinking_mode == "enabled":
        kwargs["model_kwargs"] = {
            "reasoning_effort": settings.deepseek_reasoning_effort,
        }
    return ChatDeepSeek(**kwargs)
