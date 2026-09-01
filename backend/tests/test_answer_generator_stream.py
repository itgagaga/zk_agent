import asyncio
import json

from backend.agents.answer_generator import AnswerGenerator
from backend.utils.llm_content import extract_text_content


class _Chunk:
    def __init__(self, content, *, reasoning_content=None, finish_reason=None):
        self.content = content
        self.additional_kwargs = {}
        if reasoning_content is not None:
            self.additional_kwargs["reasoning_content"] = reasoning_content
        self.response_metadata = {}
        if finish_reason is not None:
            self.response_metadata["finish_reason"] = finish_reason


class _LLM:
    def __init__(self, chunks):
        self.chunks = chunks
        self.prompts = []

    async def astream(self, prompt):
        self.prompts.append(prompt)
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


def test_stream_diagnoses_reasoning_only_length_completion(caplog):
    generator = _generator(
        _LLM([_Chunk("", reasoning_content="正在分析问题", finish_reason="length")])
    )

    asyncio.run(
        _collect(
            generator.generate_stream(
                "学习建议",
                {
                    "rag_hits": [{"title": "培养方案", "snippet": "课程"}],
                    "retrieval_summary": {"trace_id": "trace-reasoning-only"},
                },
            )
        )
    )

    assert "answer_stream_empty" in caplog.text
    assert "trace-reasoning-only" in caplog.text
    assert "finish_reason=length" in caplog.text
    assert "reasoning_chunks=1" in caplog.text


def _duplicate_source_evidence():
    return {
        "evidence_mode": "composite",
        "rag_hits": [
            {
                "title": "本科招生章程",
                "url": "https://example.edu/charter.htm#section-1",
                "chunk_id": "charter-1",
                "doc_id": "charter",
                "snippet": "排名最靠前的片段",
            },
            {
                "title": "本科招生章程",
                "url": "https://example.edu/charter.htm#section-2",
                "chunk_id": "charter-2",
                "doc_id": "charter",
                "snippet": "同一来源的另一片段",
            },
        ],
    }


def test_non_stream_deduplicates_only_display_sources():
    generator = _generator(_LLM([]))
    captured: dict[str, str] = {}

    async def fake_call(prompt: str) -> str:
        captured["prompt"] = prompt
        return "基于全部片段生成的回答"

    generator._call_llm = fake_call
    result = asyncio.run(generator.generate("本科招生章程是什么？", _duplicate_source_evidence()))

    assert len(result["sources"]) == 1
    assert result["sources"][0]["chunk_id"] == "charter-1"
    assert result["confidence"] == "high"
    assert "排名最靠前的片段" in captured["prompt"]
    assert "同一来源的另一片段" in captured["prompt"]


def test_stream_deduplicates_only_meta_sources():
    llm = _LLM([_Chunk("基于全部片段生成的回答")])
    generator = _generator(llm)

    events = _events(
        asyncio.run(
            _collect(
                generator.generate_stream(
                    "本科招生章程是什么？",
                    _duplicate_source_evidence(),
                )
            )
        )
    )

    meta = next(event for event in events if event["type"] == "meta")
    assert len(meta["sources"]) == 1
    assert meta["sources"][0]["chunk_id"] == "charter-1"
    assert meta["confidence"] == "high"
    assert "排名最靠前的片段" in llm.prompts[0]
    assert "同一来源的另一片段" in llm.prompts[0]


def test_display_source_deduplication_ignores_url_fragment():
    sources = [
        {"title": "办事指南第一处", "url": "https://example.edu/guide/#part-a"},
        {"title": "办事指南第二处", "url": "https://example.edu/guide#part-b"},
    ]

    assert AnswerGenerator._deduplicate_display_sources(sources) == [sources[0]]


async def _collect(stream):
    return [chunk async for chunk in stream]
