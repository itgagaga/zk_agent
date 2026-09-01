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


def test_composite_prompt_requires_specific_personal_facts_before_advice():
    prompt = build_qa_prompt(
        "我是信计大一新生，有什么学习建议？",
        user_sources=[
            {
                "title": "我的信息与计算科学培养方案",
                "snippet": "大一课程包括高等数学、程序设计，课程有对应学分和学期安排。",
            }
        ],
        evidence_mode="composite",
    )

    assert "个人资料主要依据" in prompt
    assert "具体事实" in prompt
    assert "明确区分“文档事实”和“基于事实的建议”" in prompt


def test_prompt_suppresses_unrelated_domain_and_tool_diagnostics():
    prompt = build_qa_prompt(
        "学校有哪些教学机构？",
        sources=[{"title": "教学机构", "snippet": "学校设有多个教学单位。"}],
        evidence_mode="composite",
    )

    assert "只回答当前问题实际涉及的内容" in prompt
    assert "不要说明哪些领域未涉及" in prompt
    assert "哪些工具或 Agent 未调用" in prompt
    assert "不要为这些内容生成空小节" in prompt


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
