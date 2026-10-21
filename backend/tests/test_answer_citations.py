import asyncio
import json
from types import SimpleNamespace

import pytest

from backend.agents.answer_generator import AnswerGenerator
from backend.api.chat import ChatResponse


def _evidence():
    return {
        "evidence_mode": "composite",
        "rag_hits": [
            {"title": title, "url": f"https://example.edu/{index}", "snippet": title}
            for index, title in enumerate([
                "医药费报销审核注意事项", "机修工", "2024培养方案总览", "学生下载",
                "学院联系方式", "本科专业目录", "分析检验员", "硕士招生章程",
            ])
        ],
        "doc_hits": [{
            "title": "信计培养方案", "doc_id": "xj", "url": "",
            "snippet": "信息与计算科学专业必修课程包括数学分析、程序设计。",
        }],
    }


def _generator(answer):
    class LLM:
        async def astream(self, prompt):
            # 引用标记可以被任意拆分到多个 SSE token。
            for char in answer:
                yield SimpleNamespace(content=char)

    generator = AnswerGenerator.__new__(AnswerGenerator)
    generator.llm = LLM()

    async def call(prompt):
        return answer

    generator._call_llm = call
    return generator


def test_curriculum_answer_only_displays_cited_personal_document():
    generator = _generator("信计必修课包括数学分析、程序设计。[9]")
    result = asyncio.run(generator.generate("信计培养方案有哪些必修课？", _evidence()))

    assert [source["title"] for source in result["sources"]] == ["信计培养方案"]
    assert result["sources"][0]["citation_id"] == 9
    assert result["confidence"] == "medium"
    # 非流式 API 校验后仍保留编号，列表编号与正文一致。
    assert ChatResponse(**result).sources[0].citation_id == 9


def test_stream_waits_for_answer_before_publishing_used_sources():
    async def scenario():
        generator = _generator("信计课程包括数学分析。[9]")
        return [json.loads(chunk.removeprefix("data: ")) async for chunk in
                generator.generate_stream("信计培养方案？", _evidence())]

    events = asyncio.run(scenario())
    assert events[0]["sources"] == []
    assert events[0]["attachments"] == []
    assert events[-1] == {"type": "done"}
    assert events[-2]["type"] == "meta"
    assert [source["title"] for source in events[-2]["sources"]] == ["信计培养方案"]
    assert events[-2]["sources"][0]["citation_id"] == 9


@pytest.mark.parametrize("answer", [
    "未找到可靠依据。", "信计培养方案", "代码示例 `[9]`", "```text\n[9]\n```",
    "~~~\n[9]\n~~~", "[9](https://example.edu)", "![9](image.png)",
    "无效引用。[99]", "引用定义\n[9]: https://example.edu",
])
def test_uncited_or_invalid_markers_never_restore_all_retrieved_sources(answer):
    result = asyncio.run(_generator(answer).generate("信计培养方案？", _evidence()))
    assert result["sources"] == []
    assert result["confidence"] == "low"


def test_multiple_citations_keep_original_numbers_and_deduplicate_documents():
    evidence = _evidence()
    evidence["doc_hits"].append({
        "title": "信计培养方案", "doc_id": "xj", "snippet": "第二个课程片段",
    })
    result = asyncio.run(_generator("培养方案及总览。[9][3][9]").generate("信计？", evidence))
    assert [source["citation_id"] for source in result["sources"]] == [3, 9]
    assert result["confidence"] == "high"


def test_tools_use_same_citation_ids_and_only_cited_attachments_are_returned():
    evidence = {
        "evidence_mode": "tool",
        "tool_results": [{"tool": "download_search", "items": [
            {"title": "信计培养方案", "file_url": "https://example.edu/xj.pdf"},
            {"title": "报销表", "file_url": "https://example.edu/expense.doc"},
        ]}],
    }
    generator = _generator("下载信计培养方案。[1]")
    captured = {}

    async def call(prompt):
        captured["prompt"] = prompt
        return "下载信计培养方案。[1]"

    generator._call_llm = call
    result = asyncio.run(generator.generate("下载信计培养方案", evidence))
    assert [source["title"] for source in result["sources"]] == ["信计培养方案"]
    assert [item["name"] for item in result["attachments"]] == ["信计培养方案"]
    assert result["sources"][0]["url"] == "https://example.edu/xj.pdf"
    assert "引用编号：[1]" in captured["prompt"]
    assert "引用编号：[2]" in captured["prompt"]
    assert "citation_id" not in evidence["tool_results"][0]["items"][0]


def test_generation_failure_does_not_claim_retrieved_sources_were_used():
    async def scenario():
        generator = _generator("")
        generator.llm = None
        return [json.loads(chunk.removeprefix("data: ")) async for chunk in
                generator.generate_stream("信计培养方案？", _evidence())]

    events = asyncio.run(scenario())
    assert all(event["sources"] == [] for event in events if event["type"] == "meta")
