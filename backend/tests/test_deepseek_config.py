import sys
import types

from backend.utils import deepseek


def test_deepseek_chat_disables_thinking_by_default(monkeypatch):
    captured = {}

    class FakeChatDeepSeek:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "langchain_deepseek",
        types.SimpleNamespace(ChatDeepSeek=FakeChatDeepSeek),
    )
    monkeypatch.setattr(deepseek.settings, "deepseek_thinking_mode", "disabled")

    deepseek.create_deepseek_chat(model="deepseek-v4-flash", max_tokens=2000, temperature=0.3)

    assert captured["extra_body"] == {"thinking": {"type": "disabled"}}
    assert captured["temperature"] == 0.3
    assert "model_kwargs" not in captured


def test_deepseek_chat_keeps_reasoning_effort_explicit_when_enabled(monkeypatch):
    captured = {}

    class FakeChatDeepSeek:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "langchain_deepseek",
        types.SimpleNamespace(ChatDeepSeek=FakeChatDeepSeek),
    )
    monkeypatch.setattr(deepseek.settings, "deepseek_thinking_mode", "enabled")
    monkeypatch.setattr(deepseek.settings, "deepseek_reasoning_effort", "low")

    deepseek.create_deepseek_chat(model="deepseek-v4-flash", max_tokens=2000, temperature=0.3)

    assert captured["extra_body"] == {"thinking": {"type": "enabled"}}
    assert captured["model_kwargs"] == {"reasoning_effort": "low"}
    assert "temperature" not in captured
