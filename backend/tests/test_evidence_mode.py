import asyncio

from backend.agents.answer_generator import AnswerGenerator
from backend.rag.prompt_templates import build_qa_prompt


def test_prompt_uses_evidence_mode_when_legacy_priority_conflicts():
    prompt = build_qa_prompt(
        "网络报障电话是多少？",
        sources=[{"title": "官网联系方式", "snippet": "网络中心电话"}],
        tool_results=[
            {
                "tool": "contact_search",
                "items": [{"title": "网络报障电话", "phone": "020-12345678"}],
            }
        ],
        evidence_mode="composite",
        evidence_priority="rag",
    )

    assert "【官网资料 · 政策 Agent】" in prompt
    assert "【多 Agent 协作取证 · 按领域分区使用】" in prompt
    assert "020-12345678" in prompt


def test_answer_generator_exposes_mode_and_keeps_legacy_priority_compatibility():
    generator = object.__new__(AnswerGenerator)
    captured: dict[str, str] = {}

    async def fake_call(prompt: str) -> str:
        captured["prompt"] = prompt
        return "基于证据的回答"

    generator._call_llm = fake_call
    result = asyncio.run(
        generator.generate(
            "网络报障电话是多少？",
            {
                "evidence_mode": "composite",
                "evidence_priority": "rag",
                "rag_hits": [
                    {
                        "title": "官网联系方式",
                        "snippet": "网络中心电话",
                    }
                ],
                "tool_results": [
                    {
                        "tool": "contact_search",
                        "items": [{"title": "网络报障电话", "phone": "020-12345678"}],
                    }
                ],
            },
        )
    )

    assert result["evidence_mode"] == "composite"
    assert result["evidence_priority"] == "rag"
    assert "020-12345678" in captured["prompt"]
