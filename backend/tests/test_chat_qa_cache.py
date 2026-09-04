import asyncio
import json

from backend.api import chat
from backend.cache.qa_file_cache import CachedAnswer


def _events(chunks):
    return [
        json.loads(line[6:])
        for chunk in chunks
        for line in chunk.splitlines()
        if line.startswith("data: ")
    ]


def test_stream_cache_hit_skips_controller(monkeypatch):
    class FakeCache:
        async def get_answer(self, question):
            return CachedAnswer("文件回答", "preset/demo.md", "preset")

    class BrokenController:
        def __init__(self):
            raise AssertionError("缓存命中时不应创建 AgentController")

    monkeypatch.setattr(chat, "qa_cache", FakeCache())
    monkeypatch.setattr(chat, "AgentController", BrokenController)

    async def collect():
        response = await chat.chat_stream(chat.ChatRequest(question="固定问题"), None)
        return [chunk async for chunk in response.body_iterator]

    events = _events(asyncio.run(collect()))
    assert [event["type"] for event in events] == ["meta", "token", "done"]
    assert events[0]["cache_hit"] is True
    assert events[1]["content"] == "文件回答"


def test_stream_cache_miss_saves_completed_answer(monkeypatch):
    class FakeCache:
        def __init__(self):
            self.saved = None

        async def get_answer(self, question):
            return None

        async def save_generated_answer(self, question, answer):
            self.saved = (question, answer)
            return "generated/demo.md"

    class FakeController:
        async def handle_stream(self, *args, **kwargs):
            yield 'data: {"type":"meta","fallback":false}\n\n'
            yield 'data: {"type":"token","content":"第一段"}\n\n'
            yield 'data: {"type":"token","content":"第二段"}\n\n'
            yield 'data: {"type":"done"}\n\n'

    fake_cache = FakeCache()
    monkeypatch.setattr(chat, "qa_cache", fake_cache)
    monkeypatch.setattr(chat, "AgentController", FakeController)

    async def collect():
        response = await chat.chat_stream(chat.ChatRequest(question="动态问题"), None)
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(collect())
    assert fake_cache.saved == ("动态问题", "第一段第二段")
    assert _events(chunks)[-1] == {"type": "done"}


def test_non_stream_cache_miss_saves_answer(monkeypatch):
    class FakeCache:
        def __init__(self):
            self.saved = None

        async def get_answer(self, question):
            return None

        async def save_generated_answer(self, question, answer):
            self.saved = (question, answer)
            return "generated/demo.md"

    class FakeController:
        async def handle(self, *args, **kwargs):
            return {"answer": "模型回答", "confidence": "medium", "fallback": False}

    fake_cache = FakeCache()
    monkeypatch.setattr(chat, "qa_cache", fake_cache)
    monkeypatch.setattr(chat, "AgentController", FakeController)

    result = asyncio.run(chat.chat(chat.ChatRequest(question="动态问题"), None))

    assert result.answer == "模型回答"
    assert fake_cache.saved == ("动态问题", "模型回答")
