import asyncio
import json

from backend.api import chat


def test_chat_stream_emits_error_and_done_when_controller_fails(monkeypatch):
    class BrokenController:
        async def handle_stream(self, *args, **kwargs):
            yield 'data: {"type":"router"}\n\n'
            raise RuntimeError("llm unavailable")

    monkeypatch.setattr(chat, "AgentController", BrokenController)

    async def collect():
        response = await chat.chat_stream(chat.ChatRequest(question="测试"), None)
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(collect())
    events = [json.loads(line[6:]) for chunk in chunks for line in chunk.splitlines() if line.startswith("data: ")]

    assert events[0]["type"] == "router"
    assert events[-2] == {"type": "token", "content": "回答生成失败，请稍后重试"}
    assert events[-1] == {"type": "done"}
