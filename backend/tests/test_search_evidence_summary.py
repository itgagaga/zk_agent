import asyncio

from backend.api import search


def test_rag_search_exposes_chunk_ids_and_evidence_assessment(monkeypatch):
    async def fake_search(query, top_k=None):
        return [
            {
                "chunk_id": "zsb_bkzs_zc_2026_0",
                "title": "2026年普通高考招生章程",
                "snippet": "招生计划、录取规则",
                "url": "https://example.edu/charter",
                "score": 0.9,
            }
        ]

    monkeypatch.setattr(search._retriever, "search", fake_search)

    result = asyncio.run(search.rag_search(q="2026年本科招生章程主要讲了什么", top_k=5))

    assert result.hits[0].chunk_id == "zsb_bkzs_zc_2026_0"
    assert result.retrieval_summary["evidence_assessment"]["status"] == "sufficient"


def test_rag_search_gate_ranks_charter_above_nearby_brochure(monkeypatch):
    async def fake_search(query, top_k=None):
        return [
            {
                "chunk_id": "brochure-2026",
                "title": "2026年本科招生简章",
                "snippet": "招生章程相关宣传信息。",
                "score": 0.99,
            },
            {
                "chunk_id": "charter-2026",
                "title": "2026年本科招生章程（夏季高考）",
                "snippet": "招生计划、录取规则和收费标准。",
                "score": 0.80,
            },
        ]

    monkeypatch.setattr(search._retriever, "search", fake_search)

    result = asyncio.run(search.rag_search(q="2026年本科招生章程主要讲了什么", top_k=5))

    assert result.hits[0].chunk_id == "charter-2026"
