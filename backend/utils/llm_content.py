"""统一处理 LangChain/OpenAI 消息和流式内容块。"""
from __future__ import annotations

from typing import Any


def extract_text_content(value: Any) -> str:
    """从字符串、消息对象或结构化内容块中提取纯文本。

    LangChain 及不同模型适配器可能返回字符串、``AIMessage``、内容块列表，
    或带 ``text``/``content`` 字段的字典。所有 LLM 调用方都应通过此函数
    消费结果，避免某个入口单独处理导致输出为空或出现 ``[object Object]``。
    """
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        nested = content.get("text")
        if nested is None:
            nested = content.get("content")
        return extract_text_content(nested) if nested is not None else ""
    if isinstance(content, (list, tuple)):
        return "".join(extract_text_content(item) for item in content)
    return "" if content is None else str(content)
