import asyncio

import pytest

from backend.agents.controller import AgentController
from backend.rag.query_planner import QueryPlanner
from backend.rag.retrieval_manager import RetrievalManager


GOLDEN_CASES = [
    ("缓考申请表在哪里下载？", {"download_search", "campus_rag"}),
    ("学生证补办需要什么材料？", {"download_search", "campus_rag"}),
    ("学籍异动流程在哪里看？", {"download_search", "campus_rag"}),
    ("网络报障电话是多少？", {"contact_search", "service_link_search", "campus_rag"}),
    ("招生章程在哪里？", {"campus_rag"}),
    ("本科专业目录有哪些？", {"major_search", "campus_rag"}),
    ("研究生调剂要求是什么？", {"campus_rag"}),
    ("校医院医保报销怎么处理？", {"contact_search", "campus_rag"}),
    ("缓考申请表在哪里下载，那申请条件呢？", {"download_search", "campus_rag"}),
    ("从海珠校区到白云校区怎么走，明天天气如何？", {"map_route", "weather_search", "campus_rag"}),
]


def test_golden_queries_keep_relevant_retrievers_without_exclusive_routing():
    planner = QueryPlanner()
    for query, expected in GOLDEN_CASES:
        plan = planner.plan(query)
        assert expected.issubset(set(plan.retrievers)), query
        assert plan.allow_fallback is True


class _GoldenRetriever:
    """Deterministic local retriever for the controller acceptance cases."""

    async def search(self, query, top_k=None, where=None):
        if "本科招生章程" in query:
            if "补充检索约束" in query:
                return [{
                    "chunk_id": "zsb_bkzs_zc_2026_001",
                    "doc_id": "zsb_bkzs_zc_2026",
                    "title": "2026年本科招生章程（夏季高考）",
                    "snippet": "招生计划、录取规则、收费标准和其他说明。",
                    "score": 0.82,
                }]
            return [{
                "chunk_id": "zsb_yjs_zc_2026_001",
                "doc_id": "zsb_yjs_zc_2026",
                "title": "2026年硕士研究生招生章程",
                "snippet": "研究生报名和复试要求。",
                "score": 0.95,
            }]
        if "缓考申请表" in query:
            return [{
                "chunk_id": "jwc_student_download_001",
                "doc_id": "jwc_student_download",
                "title": "教务部学生下载栏目资料清单",
                "snippet": "缓考申请表下载及申请条件说明。",
                "score": 0.9,
            }]
        return [{
            "chunk_id": "campus_general_001",
            "doc_id": "campus_general",
            "title": "校园服务说明",
            "snippet": "学校提供校园综合服务。",
            "score": 0.6,
        }]

    async def search_documents(self, query, top_k=None, where=None, user_id=None):
        return []


class _GoldenTool:
    def __init__(self, title, snippet):
        self.title = title
        self.snippet = snippet

    async def run(self, question, **kwargs):
        return {
            "items": [{
                "id": self.title,
                "title": self.title,
                "snippet": self.snippet,
                "file_url": f"/golden/{self.title}.pdf",
            }],
            "total": 1,
        }


class _GoldenAnswerGenerator:
    async def generate(self, question, evidence, history=None):
        sources = []
        for hit in evidence.get("rag_hits", []) + evidence.get("doc_hits", []):
            sources.append({"title": hit.get("title"), "chunk_id": hit.get("chunk_id")})
        for result in evidence.get("tool_results", []):
            for item in result.get("items", []):
                sources.append({"title": item.get("title"), "url": item.get("file_url")})
        return {"answer": "基于本地黄金测试证据", "sources": sources, "fallback": False}

    async def generate_stream(self, question, evidence, history=None):
        import json

        yield "data: " + json.dumps({
            "type": "meta",
            "sources": [],
            "retrieval_summary": evidence.get("retrieval_summary", {}),
        }, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "token", "content": "基于本地黄金测试证据"}, ensure_ascii=False) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"


def _golden_controller():
    controller = AgentController()
    controller.retrieval_manager = RetrievalManager(
        retriever=_GoldenRetriever(),
        tools={
            "download_search": _GoldenTool("缓考申请表", "下载入口和申请条件"),
            "contact_search": _GoldenTool("网络报障电话", "网络故障报修联系方式"),
            "service_link_search": _GoldenTool("网络报障服务入口", "在线报障入口"),
            "weather_search": _GoldenTool("广州天气", "今日天气和气温"),
            "map_route": _GoldenTool("校区路线", "从海珠校区到白云校区的路线"),
        },
    )
    controller.answer_generator = _GoldenAnswerGenerator()
    return controller


@pytest.mark.parametrize(
    ("query", "expected_title"),
    [
        ("缓考申请表在哪里下载？", "教务部学生下载栏目资料清单"),
        ("2026年本科招生章程主要讲了什么？", "2026年本科招生章程（夏季高考）"),
        ("网络报障电话是多少？", "网络报障电话"),
        ("从海珠校区到白云校区怎么走，明天天气如何？", "校区路线"),
    ],
)
def test_golden_cases_reach_controller_answer_without_exclusive_routing(query, expected_title):
    result = asyncio.run(_golden_controller().handle(query))

    assert result["fallback"] is False
    assert any(source.get("title") == expected_title for source in result["sources"])
    assert result["retrieval_summary"]["evidence_assessment"]["status"] == "supported"


def test_stream_no_longer_emits_supervisor_priority_event():
    events = asyncio.run(_collect_stream(_golden_controller(), "缓考申请表在哪里下载？"))
    assert not any(event.get("type") == "supervisor" for event in events)
    assert any(event.get("type") == "retrieval" for event in events)


async def _collect_stream(controller, query):
    import json

    events = []
    async for chunk in controller.handle_stream(query):
        for line in chunk.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events
