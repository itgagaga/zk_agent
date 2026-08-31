import asyncio
import json

from backend.agents.answer_generator import AnswerGenerator
from backend.utils.llm_content import extract_text_content


class _Chunk:
    def __init__(self, content):
        self.content = content


class _LLM:
    def __init__(self, chunks):
        self.chunks = chunks

    async def astream(self, prompt):
        for chunk in self.chunks:
            yield chunk


def _events(chunks):
    return [
        json.loads(line[6:])
        for chunk in chunks
        for line in chunk.splitlines()
        if line.startswith("data: ")
    ]


def _generator(llm):
    generator = AnswerGenerator.__new__(AnswerGenerator)
    generator.llm = llm
    return generator


def test_extract_text_content_handles_common_llm_shapes():
    class Message:
        content = [{"type": "text", "text": "第一段"}, {"content": "第二段"}]

    assert extract_text_content(Message()) == "第一段第二段"


def test_stream_normalizes_structured_content_blocks():
    generator = _generator(
        _LLM([_Chunk([{"type": "text", "text": "建议先学好高数"}]), _Chunk("。")])
    )

    events = _events(
        asyncio.run(
            _collect(
                generator.generate_stream(
                    "学习建议",
                    {"rag_hits": [{"title": "培养方案", "snippet": "课程"}]},
                )
            )
        )
    )

    assert [event["content"] for event in events if event["type"] == "token"] == [
        "建议先学好高数",
        "。",
    ]
    assert events[-1] == {"type": "done"}


def test_stream_does_not_finish_with_an_empty_answer():
    generator = _generator(_LLM([_Chunk(""), _Chunk([])]))

    events = _events(
        asyncio.run(
            _collect(
                generator.generate_stream(
                    "学习建议",
                    {"rag_hits": [{"title": "培养方案", "snippet": "课程"}]},
                )
            )
        )
    )

    assert events[-2] == {"type": "token", "content": "模型未返回有效回答，请重试。"}
    assert events[-1] == {"type": "done"}


async def _collect(stream):
    return [chunk async for chunk in stream]
