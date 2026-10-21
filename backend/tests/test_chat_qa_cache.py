import asyncio
import json

import pytest

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

        async def save_generated_answer(self, question, answer, *, metadata=None):
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

        async def save_generated_answer(self, question, answer, *, metadata=None):
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


@pytest.mark.parametrize("stream", [False, True])
def test_generated_cache_hit_retains_only_actual_sources(monkeypatch, stream):
    source = {"title": "信计培养方案", "url": "", "citation_id": 9}

    class FakeCache:
        async def get_answer(self, question):
            return CachedAnswer("数学分析。[9]", "answers.json", "generated", {
                "citation_version": 1, "sources": [source], "confidence": "medium",
            })

    class BrokenController:
        def __init__(self):
            raise AssertionError("缓存命中时不应创建 AgentController")

    monkeypatch.setattr(chat, "qa_cache", FakeCache())
    monkeypatch.setattr(chat, "AgentController", BrokenController)

    async def scenario():
        req = chat.ChatRequest(question="信计必修课？")
        if stream:
            response = await chat.chat_stream(req, None)
            events = _events([chunk async for chunk in response.body_iterator])
            return events[0]
        return (await chat.chat(req, None)).model_dump()

    result = asyncio.run(scenario())
    assert result["sources"][0]["title"] == "信计培养方案"
    assert result["sources"][0]["citation_id"] == 9
    assert len(result["sources"]) == 1
    assert result["confidence"] == "medium"


def test_stream_cache_stores_final_sources_instead_of_initial_empty_meta(monkeypatch):
    source = {"title": "信计培养方案", "url": "", "citation_id": 9}

    class FakeCache:
        saved_metadata = None

        async def get_answer(self, question):
            # 旧动态缓存没有引用信息，必须重新生成。
            return CachedAnswer("旧回答", "answers.json", "generated")

        async def save_generated_answer(self, question, answer, *, metadata=None):
            self.saved_metadata = metadata

    class FakeController:
        async def handle_stream(self, *args, **kwargs):
            yield chat._sse({"type": "meta", "sources": [], "confidence": "low"})
            yield chat._sse({"type": "token", "content": "数学分析。[9]"})
            yield chat._sse({"type": "meta", "sources": [source], "confidence": "medium"})
            yield chat._sse({"type": "done"})

    cache = FakeCache()
    monkeypatch.setattr(chat, "qa_cache", cache)
    monkeypatch.setattr(chat, "AgentController", FakeController)

    async def scenario():
        response = await chat.chat_stream(chat.ChatRequest(question="信计必修课？"), None)
        return [chunk async for chunk in response.body_iterator]

    asyncio.run(scenario())
    assert cache.saved_metadata["sources"] == [source]
    assert cache.saved_metadata["confidence"] == "medium"
    assert cache.saved_metadata["citation_version"] == 1


@pytest.mark.parametrize("kwargs", [
    {"knowledge_scope": "with_personal"}, {"knowledge_scope": "personal_only"},
    {"history": [{"role": "user", "content": "信计培养方案"}]},
    {"context_hint": "信计专业"},
])
def test_context_dependent_answers_do_not_share_question_only_source_cache(kwargs):
    assert not chat._cache_eligible(chat.ChatRequest(question="必修课？", **kwargs))
