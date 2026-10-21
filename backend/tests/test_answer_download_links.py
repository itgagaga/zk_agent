"""资料下载链接与来源编号应同时保留，包括小对话使用的 SSE 路径。"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from backend.agents.answer_generator import AnswerGenerator


FORM_URL = "https://example.edu/info/1099/4092.htm"
FLOW_URL = "https://example.edu/info/1099/28032.htm"
PAGE_URL = "https://example.edu/student-downloads.htm"
ANSWER = (
    f"1. [补办学生证申请表（2024版）]({FORM_URL})。[1]\n"
    f"2. [补办学生证流程图（2024版）]({FLOW_URL})。[1]"
)


def _evidence(mode):
    return {
        "evidence_mode": mode,
        "rag_hits": [{
            "title": "学生下载", "url": PAGE_URL,
            "snippet": (
                f"补办学生证申请表（2024版）：{FORM_URL}\n"
                f"补办学生证流程图（2024版）：{FLOW_URL}"
            ),
        }],
        "tool_results": [{"tool": "download_search", "items": [
            {"title": "补办学生证申请表（2024版）", "file_url": FORM_URL,
             "source_page_url": PAGE_URL, "publish_date": "2024-11-19"},
            {"title": "补办学生证流程图（2024版）", "file_url": FLOW_URL,
             "source_page_url": PAGE_URL, "publish_date": "2024-11-19"},
        ]}] if mode != "rag" else [],
    }


@pytest.mark.parametrize("mode", ["rag", "tool", "affairs", "composite"])
@pytest.mark.parametrize("streaming", [False, True])
def test_download_answer_keeps_individual_links_and_citations(mode, streaming):
    prompts = []

    class LLM:
        async def ainvoke(self, prompt):
            prompts.append(prompt)
            return SimpleNamespace(content=ANSWER)

        async def astream(self, prompt):
            prompts.append(prompt)
            # Markdown 地址和引用均可能跨 token。
            for char in ANSWER:
                yield SimpleNamespace(content=char)

    generator = AnswerGenerator.__new__(AnswerGenerator)
    generator.llm = LLM()

    async def run():
        if not streaming:
            return await generator.generate("补办学生证需要什么材料？", _evidence(mode))
        events = [json.loads(chunk.removeprefix("data: ")) async for chunk in
                  generator.generate_stream("补办学生证需要什么材料？", _evidence(mode))]
        return {**events[-2], "answer": "".join(
            event["content"] for event in events if event["type"] == "token"
        )}

    result = asyncio.run(run())
    assert result["answer"] == ANSWER
    assert [source["citation_id"] for source in result["sources"]] == [1]
    prompt = prompts[0]
    assert FORM_URL in prompt and FLOW_URL in prompt
    assert "必须使用 Markdown 链接" in prompt
    assert "不能替代可点击链接" in prompt
    assert "不得猜测、拼接或编造链接" in prompt
    if mode != "rag":
        assert f"资料下载入口：{FORM_URL}" in prompt
        assert f"来源页面：{PAGE_URL}" in prompt


def test_missing_download_url_does_not_get_a_fabricated_entry():
    from backend.rag.prompt_templates import build_qa_prompt

    prompt = build_qa_prompt("补办学生证申请表", evidence_mode="tool", tool_results=[{
        "tool": "download_search", "items": [{"title": "学生证申请表"}],
    }])
    assert "资料名称：学生证申请表" in prompt
    assert "资料下载入口：" not in prompt
    assert "没有地址时如实说明未提供链接" in prompt
