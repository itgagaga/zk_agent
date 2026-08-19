# RAG 与多 Agent 编排简化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前排他式 Router/Supervisor 链路改造成单 Orchestrator 驱动的非排他检索、证据融合与可验证回答流水线。

**Architecture:** 保留 `AgentController` 作为入口，新增 Query Planner、Retrieval Manager 和 Evidence Fusion。普通校园问题默认执行官网 RAG，结构化工具和实时 API 作为并行证据源；按子问题融合证据，不再按来源类型全局裁决。

**Tech Stack:** Python 3.12+/FastAPI/Pydantic/Chroma/sentence-transformers/pytest；不新增外部 Agent 框架或向量数据库。

**Spec:** `docs/superpowers/specs/2026-08-19-rag-orchestration-simplification-design.md`

## Global Constraints

- 不引入 LangGraph 或新的 Agent 框架。
- 不增加新的外部向量数据库。
- 不以更大的 Top-K、调整 Prompt 或降低阈值作为主要修复。
- 不在第一阶段引入额外 LLM reranker；先使用可复现的确定性融合。
- 不改变聊天 API 的核心响应字段和前端 `meta/token/done` SSE 契约。
- 所有阶段保持应用可运行；旧 Router/Supervisor 只有在新链路回归通过后才删除。
- 用户文档检索必须始终按 `user_id` 隔离；不得把其他用户的 chunk 合并进当前结果。

## File Map

- Create `backend/rag/contracts.py`: `SubQuestion`、`RetrievalPlan`、`Evidence`、`EvidenceBundle`。
- Create `backend/rag/query_planner.py`: 非排他查询规划与多轮上下文补全。
- Create `backend/rag/retrieval_manager.py`: 并行调用 RAG、文档、结构化工具和实时工具。
- Create `backend/rag/evidence_fusion.py`: 证据归一化、RRF、去重、Parent 扩展和覆盖检查。
- Modify `backend/tools/base.py` and structured tools: 字段加权评分、排序、统一证据输出。
- Modify `backend/rag/vector_store.py` and `backend/rag/retriever.py`: 过召回、混合候选、去重补位、权限安全。
- Modify `backend/agents/controller.py`: 固定 Orchestrator 流程，保留 SSE 兼容事件。
- Modify `backend/agents/answer_generator.py` and `backend/rag/prompt_templates.py`: 使用融合证据和覆盖状态。
- Modify `crawler/chunking.py`, `crawler/build_kb.py`: 稳定文档 ID、索引一致性和切分配置。
- Modify `frontend/src/chatStore.js`, `frontend/src/embeddedChatStore.js`, chat components: 阶段 4 删除旧编排展示字段。
- Create/modify `backend/tests/test_evidence_contract.py`, `test_structured_retrieval.py`, `test_evidence_fusion.py`, `test_orchestrator_retrieval.py`, `test_rag_retrieval.py`.
- Create `frontend/src/retrievalSummary.js` and `frontend/src/retrievalSummary.test.js`: pure SSE metadata merge helper and its Node test.
- Modify `analytics/evaluation.py`, `analytics/run_analysis.py`: 用稳定 ID 和端到端指标。

---

### Task 1: 建立失败基线与统一证据契约

**Files:**
- Create: `backend/rag/contracts.py`
- Create: `backend/tests/test_evidence_contract.py`
- Create: `backend/tests/test_orchestrator_retrieval.py`

**Interfaces:**
- `SubQuestion(id: str, text: str, filters: dict[str, str] = Field(default_factory=dict), required_sources: list[str] = Field(default_factory=list))`
- `RetrievalPlan(original_question: str, normalized_question: str, subquestions: list[SubQuestion], retrievers: list[str], pure_live: bool = False)`
- `Evidence(evidence_id: str, source_type: str, source_name: str, title: str, content: str, url: str = "", doc_id: str | None = None, parent_id: str | None = None, relevance_score: float = 0.0, authority_score: float = 0.0, freshness_score: float = 0.0, matched_fields: list[str] = Field(default_factory=list), subquestion_id: str = "", metadata: dict[str, Any] = Field(default_factory=dict))`
- `EvidenceBundle(evidences: list[Evidence], coverage: dict[str, float], conflicts: list[dict[str, Any]], independent_source_count: int, fallback_reason: str | None = None)`
- Each model exposes `model_dump()` and `to_source_dict()` so existing `AnswerGenerator` can receive plain dictionaries during migration.

- [ ] **Step 1: Write failing contract tests**

```python
def test_evidence_to_source_dict_preserves_score_and_identity():
    evidence = Evidence(
        evidence_id="campus:doc-1:chunk-2",
        source_type="campus_rag",
        source_name="campus_rag",
        title="招生章程",
        content="报考条件……",
        doc_id="doc-1",
        relevance_score=0.82,
        subquestion_id="q1",
    )
    result = evidence.to_source_dict()
    assert result["evidence_id"] == "campus:doc-1:chunk-2"
    assert result["relevance_score"] == 0.82

def test_download_item_can_be_normalized_to_evidence():
    evidence = Evidence.from_tool_item(
        source_name="download_search",
        item={"title": "缓考申请表", "file_url": "/file.pdf"},
        subquestion_id="q1",
    )
    assert evidence.source_type == "structured"
    assert evidence.url == "/file.pdf"
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `python -m pytest backend/tests/test_evidence_contract.py -q -p no:cacheprovider`

Expected: FAIL because `backend.rag.contracts` and conversion methods do not exist.

- [ ] **Step 3: Implement the models and conversion helpers**

Use Pydantic v2 models with `Field(default_factory=...)`; never use mutable list/dict defaults. `from_tool_item()` must derive URL from `file_url`, `source_page_url`, or `url`, and must never fabricate a URL.

- [ ] **Step 4: Add the regression fixture for the known failure**

The fixture represents 20 download candidates where the relevant item is rank 19, plus a RAG candidate containing the answer. It is a stable input fixture consumed by the orchestration tests in Task 5.

```python
LATE_MATCH_CASE = {
    "tool_items": [{"title": f"noise-{i}"} for i in range(18)] + [{"title": "缓考申请表"}],
    "rag_items": [{"title": "学生下载", "snippet": "缓考申请表下载入口"}],
}

def test_late_match_fixture_contains_both_evidence_sources():
    tool_items = LATE_MATCH_CASE["tool_items"]
    rag_items = LATE_MATCH_CASE["rag_items"]
    assert len(tool_items) == 19
    assert "缓考申请表" in [item["title"] for item in tool_items]
    assert "缓考申请表下载入口" in rag_items[0]["snippet"]
```

- [ ] **Step 5: Run tests and commit**

Run: `python -m pytest backend/tests/test_evidence_contract.py -q -p no:cacheprovider`

Commit: `git add backend/rag/contracts.py backend/tests/test_evidence_contract.py backend/tests/test_orchestrator_retrieval.py; git commit -m "feat: add retrieval evidence contracts"`

---

### Task 2: 修复结构化检索排序和噪声匹配

**Files:**
- Modify: `backend/tools/base.py`
- Modify: `backend/tools/download_tool.py`
- Modify: `backend/tools/contact_tool.py`
- Modify: `backend/tools/major_tool.py`
- Modify: `backend/tools/service_link_tool.py`
- Modify: `backend/tools/job_tool.py`
- Create: `backend/tests/test_structured_retrieval.py`

**Interfaces:**
- Add `BaseTool.score_item(question: str, item: dict[str, Any], *, title_fields: tuple[str, ...], body_fields: tuple[str, ...]) -> tuple[float, list[str]]`.
- Keep each tool's public `run(question, **kwargs)` return shape during migration, adding `relevance_score`, `matched_fields`, and `evidence_id` to each item.
- Use `normalize_query()` to remove punctuation and stop words without generating all 2-grams as independent OR conditions.

- [ ] **Step 1: Write failing ranking tests**

```python
@pytest.mark.asyncio
async def test_download_exact_title_beats_common_download_word(monkeypatch):
    monkeypatch.setattr(DownloadTool, "_load_all_metadata", lambda: [
        {"source_url": "u", "download_items": [
            {"name": "普通下载说明", "url": "noise"},
            {"name": "缓考申请表", "url": "target"},
        ]}
    ])
    result = await DownloadTool().run("缓考申请表在哪里下载？", top_k=1)
    assert result["items"][0]["title"] == "缓考申请表"
    assert "title_exact" in result["items"][0]["matched_fields"]

@pytest.mark.asyncio
async def test_contact_query_does_not_return_unrelated_departments_first(monkeypatch):
    monkeypatch.setattr(ContactTool, "_load_all_metadata", lambda: [
        {"source_url": "u", "contacts": [
            {"department": "饮食科", "phone": "1"},
            {"department": "网络报障", "phone": "2"},
        ]}
    ])
    result = await ContactTool().run("网络报障电话是多少", top_k=1)
    assert result["items"][0]["title"] == "网络报障"
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `python -m pytest backend/tests/test_structured_retrieval.py -q -p no:cacheprovider`

Expected: FAIL because current tools use arbitrary 2-gram OR matching and preserve input order.

- [ ] **Step 3: Implement deterministic field scoring**

Implement these score rules in `BaseTool.score_item()`:

```python
score = 0.0
if normalized_query == normalized_title:
    score += 1.0
elif normalized_query in normalized_title:
    score += 0.85
elif all(token in normalized_title for token in entity_tokens):
    score += 0.70
score += 0.20 if year_token_matches else 0.0
score += 0.15 if department_token_matches else 0.0
score += 0.05 if body_matches else 0.0
```

Clamp scores to `[0.0, 1.0]`. Ignore generic tokens (`下载`, `哪里`, `学校`, `申请`, `电话`) unless accompanied by a domain token. Sort by score descending, then exact title match, then stable title/URL order. Return only after sorting and deduplication.

- [ ] **Step 4: Normalize all structured tool outputs**

Each item gets a stable ID based on tool name plus normalized URL/title. `total` remains the count before Top-K truncation. Empty/low-score results return `items=[]` so the manager can invoke RAG fallback.

- [ ] **Step 5: Run tests and the known queries**

Run: `python -m pytest backend/tests/test_structured_retrieval.py backend/tests/test_job_tool.py -q -p no:cacheprovider`

Then run the existing tools against `缓考申请表在哪里下载？`, `学生证补办规定是什么？`, and `白云校区网络报障电话是多少？`; assert the relevant item is within Top-3.

- [ ] **Step 6: Commit**

Commit: `git add backend/tools backend/tests/test_structured_retrieval.py; git commit -m "fix: rank structured retrieval results"`

---

### Task 3: 修复 RAG 过召回、去重和 Parent 补位

**Files:**
- Modify: `backend/rag/vector_store.py`
- Modify: `backend/rag/retriever.py`
- Create: `backend/tests/test_rag_retrieval.py`

**Interfaces:**
- Add `VectorStore.query(..., top_k: int, include_embeddings: bool = False) -> list[dict[str, Any]]` while preserving existing callers.
- Add `RAGRetriever.keyword_search(query: str, top_k: int = 30, collection: str = "zhku", where: dict[str, Any] | None = None) -> list[dict[str, Any]]` using stored title/section/document text and deterministic token overlap.
- Add `RAGRetriever.search(..., candidate_k: int | None = None, distinct_docs: int | None = None) -> list[dict[str, Any]]`.
- Add private helpers `_dedupe_by_document()`, `_expand_parent_hits_with_refill()`, and `_stable_hit_key()`.

- [ ] **Step 1: Write failing retrieval tests**

```python
@pytest.mark.asyncio
async def test_parent_expansion_refills_from_next_document():
    retriever = make_fake_retriever([
        child("doc-a", "p-a", 0.90), child("doc-a", "p-a", 0.89),
        child("doc-b", "p-b", 0.88), child("doc-c", "p-c", 0.87),
    ])
    hits = await retriever.search("课程", top_k=3, candidate_k=10)
    assert {hit["metadata"]["doc_id"] for hit in hits} == {"doc-a", "doc-b", "doc-c"}

@pytest.mark.asyncio
async def test_same_parent_does_not_count_as_multiple_independent_sources():
    retriever = make_fake_retriever([child("doc-a", "p-a", 0.9) for _ in range(5)])
    hits = await retriever.search("课程", top_k=5, candidate_k=15)
    assert len({hit["metadata"]["parent_id"] for hit in hits}) == 1

def test_keyword_candidates_prioritize_title_match():
    retriever = make_fake_keyword_retriever([
        {"title": "学生下载", "document": "缓考申请表下载入口"},
        {"title": "校园新闻", "document": "今天开放下载活动资料"},
    ])
    hits = retriever.keyword_search("缓考申请表", top_k=1)
    assert hits[0]["title"] == "学生下载"
```

The test module defines `child(doc_id, parent_id, score)` as a helper returning a hit with `chunk_id`, `snippet`, `score`, and `metadata={"doc_id": doc_id, "parent_id": parent_id, "chunk_role": "child"}`. `make_fake_retriever(hits)` injects a fake store whose `query()` returns those hits and whose Parent fetch returns one sibling list per parent. `make_fake_keyword_retriever(records)` injects stored records used by `keyword_search()`.

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest backend/tests/test_rag_retrieval.py -q -p no:cacheprovider`

Expected: FAIL because current search queries only requested Top-K and slices after Parent expansion without refill.

- [ ] **Step 3: Over-fetch before filtering**

For campus RAG use `candidate_k = max(top_k * 4, 30)` unless an explicit caller value is provided. Apply score thresholds to the over-fetched list, not the final list.

- [ ] **Step 3a: Add deterministic keyword candidates**

Implement `keyword_search()` without a new dependency: normalize the query and each stored document, score exact title/section matches above body token overlap, and return the top 30 with `metadata["retrieval_method"] = "keyword"`. The existing vector query sets `retrieval_method = "dense"`.

- [ ] **Step 4: Deduplicate and refill**

Merge keyword and dense candidates by stable chunk ID before grouping child hits by `doc_id + parent_id`; retain the highest scoring child as the representative, then expand only selected parents. Continue consuming ranked candidates until the requested number of independent documents or parents is reached.

- [ ] **Step 5: Preserve user document isolation**

Extend `get_chunks_by_parent_id()` and `get_chunks_by_doc_id()` to accept `user_id`; use a combined Chroma `where` clause for every follow-up fetch. Add a test proving a same-named `doc_id` from another user is never included.

- [ ] **Step 6: Run tests and current RAG cases**

Run: `python -m pytest backend/tests/test_rag_retrieval.py backend/tests/test_chunking.py -q -p no:cacheprovider`

Run the 20 `RAG_CASES` through the local retriever and record raw candidates, distinct documents, final hits, and exact/normalized ID matches.

- [ ] **Step 7: Commit**

Commit: `git add backend/rag/vector_store.py backend/rag/retriever.py backend/tests/test_rag_retrieval.py; git commit -m "fix: refill and diversify rag candidates"`

---

### Task 4: 引入 Query Planner、Retrieval Manager 和 Evidence Fusion

**Files:**
- Create: `backend/rag/query_planner.py`
- Create: `backend/rag/retrieval_manager.py`
- Create: `backend/rag/evidence_fusion.py`
- Create: `backend/tests/test_evidence_fusion.py`
- Create: `backend/tests/test_query_planner.py`

**Interfaces:**
- `QueryPlanner.plan(question: str, history: list[dict[str, str]] | None = None) -> RetrievalPlan`.
- `RetrievalManager.retrieve(plan: RetrievalPlan, *, user_id: int | None = None, history: list[dict[str, str]] | None = None) -> list[Evidence]`.
- `EvidenceFusion.fuse(question: str, plan: RetrievalPlan, candidates: list[Evidence]) -> EvidenceBundle`.

- [ ] **Step 1: Write planner tests**

```python
def test_planner_keeps_rag_for_download_policy_question():
    plan = QueryPlanner().plan("缓考申请条件和申请表在哪里下载？")
    assert "campus_rag" in plan.retrievers
    assert "download_search" in plan.retrievers

def test_planner_uses_history_for_omitted_entity():
    plan = QueryPlanner().plan(
        "那申请条件呢？",
        history=[{"role": "user", "content": "2026 年硕士招生章程"}],
    )
    assert "2026" in plan.normalized_question
    assert "硕士" in plan.normalized_question

def test_planner_uses_only_live_tool_for_pure_route_question():
    plan = QueryPlanner().plan("从广州南站到白云校区怎么走？")
    assert plan.pure_live is True
    assert plan.retrievers == ["map_route"]
```

- [ ] **Step 2: Write fusion tests**

```python
def test_fusion_keeps_rag_when_structured_result_is_irrelevant():
    plan = RetrievalPlan(
        original_question="缓考政策是什么？",
        normalized_question="缓考政策",
        subquestions=[SubQuestion(id="q1", text="缓考政策")],
        retrievers=["download_search", "campus_rag"],
    )
    irrelevant_tool = Evidence(
        evidence_id="structured:noise", source_type="structured",
        source_name="download_search", title="普通下载说明", content="下载",
        relevance_score=0.10, subquestion_id="q1",
    )
    relevant_rag = Evidence(
        evidence_id="campus:doc-1:chunk-1", source_type="campus_rag",
        source_name="campus_rag", title="学生下载", content="缓考政策说明",
        doc_id="doc-1", relevance_score=0.82, subquestion_id="q1",
    )
    bundle = EvidenceFusion().fuse("缓考政策是什么？", plan, [irrelevant_tool, relevant_rag])
    assert relevant_rag.evidence_id in {item.evidence_id for item in bundle.evidences}
    assert bundle.coverage["q1"] > 0

def test_fusion_counts_one_document_once():
    plan = RetrievalPlan(
        original_question="课程", normalized_question="课程",
        subquestions=[SubQuestion(id="q1", text="课程")], retrievers=["campus_rag"],
    )
    same_doc_chunk_1 = Evidence(
        evidence_id="campus:doc-1:chunk-1", source_type="campus_rag",
        source_name="campus_rag", title="培养方案", content="课程一",
        doc_id="doc-1", parent_id="p1", relevance_score=0.8, subquestion_id="q1",
    )
    same_doc_chunk_2 = same_doc_chunk_1.model_copy(update={
        "evidence_id": "campus:doc-1:chunk-2", "content": "课程二", "relevance_score": 0.7,
    })
    bundle = EvidenceFusion().fuse("课程", plan, [same_doc_chunk_1, same_doc_chunk_2])
    assert bundle.independent_source_count == 1
```

- [ ] **Step 3: Run focused tests and verify they fail**

Run: `python -m pytest backend/tests/test_query_planner.py backend/tests/test_evidence_fusion.py -q -p no:cacheprovider`

Expected: FAIL because the new modules and interfaces do not exist.

- [ ] **Step 4: Implement deterministic Query Planner**

Use explicit categories for campus RAG, structured lookup, live API, and academic search. Extract years with `r"20\\d{2}"`, preserve named entities from the last six user/assistant turns, and split clauses on `，`, `,`, `并且`, `以及`, `同时`. Unknown questions default to `campus_rag`.

- [ ] **Step 5: Implement Retrieval Manager**

Call independent retrievers with `asyncio.gather(..., return_exceptions=True)`. Convert every result through `Evidence.from_rag_hit()`, `Evidence.from_document_hit()`, or `Evidence.from_tool_item()`. Record exceptions as diagnostic metadata while retaining successful candidates.

- [ ] **Step 6: Implement Evidence Fusion**

Use RRF score `1 / (60 + rank)` within each source, then add only bounded authority/freshness bonuses. Never compare raw Chroma distance directly with structured scores. Deduplicate by stable evidence ID, URL, or `doc_id + parent_id`; assign each selected evidence to the subquestion it supports.

- [ ] **Step 7: Run focused tests and commit**

Run: `python -m pytest backend/tests/test_query_planner.py backend/tests/test_evidence_fusion.py backend/tests/test_evidence_contract.py -q -p no:cacheprovider`

Commit: `git add backend/rag/query_planner.py backend/rag/retrieval_manager.py backend/rag/evidence_fusion.py backend/tests/test_query_planner.py backend/tests/test_evidence_fusion.py; git commit -m "feat: add non-exclusive retrieval planning and evidence fusion"`

---

### Task 5: 接入新 Orchestrator 并保留 API/SSE 兼容

**Files:**
- Modify: `backend/agents/controller.py`
- Modify: `backend/agents/answer_generator.py`
- Modify: `backend/rag/prompt_templates.py`
- Modify: `backend/api/chat.py`
- Modify: `backend/tests/test_chat_stream.py`
- Modify: `backend/tests/test_orchestrator_retrieval.py`

**Interfaces:**
- `AgentController.handle()` and `handle_stream()` signatures remain unchanged.
- Controller internal flow becomes `plan -> retrieve -> fuse -> generate`.
- `AnswerGenerator.generate()` and `generate_stream()` consume `EvidenceBundle` converted to source dictionaries; no code reads `evidence_priority` to decide which source block exists.

- [ ] **Step 1: Add failing orchestration tests**

```python
@pytest.mark.asyncio
async def test_controller_keeps_rag_when_download_tool_has_only_noise(monkeypatch):
    controller = make_controller_with_fake_retrievers()
    result = await controller.handle("缓考政策是什么？")
    assert any("缓考" in source["title"] or "缓考" in source["snippet"] for source in result["sources"])

@pytest.mark.asyncio
async def test_stream_ends_with_done_after_new_pipeline(monkeypatch):
    events = [json.loads(line[6:]) for line in await collect_sse("学校有哪些教学机构？")]
    assert events[-1]["type"] == "done"
```

The test module defines `make_controller_with_fake_retrievers()` with a fake `RetrievalManager` returning one low-score structured item and one relevant campus-RAG `Evidence`, plus a fake `AnswerGenerator` that echoes selected sources. `collect_sse(question)` consumes `AgentController.handle_stream(question)` into a list of SSE lines; no network or LLM call is allowed.

- [ ] **Step 2: Run tests and verify the new orchestration test fails**

Run: `python -m pytest backend/tests/test_orchestrator_retrieval.py backend/tests/test_chat_stream.py -q -p no:cacheprovider`

Expected: the new test fails because Controller still invokes Router and Supervisor.

- [ ] **Step 3: Replace Controller internals**

Instantiate `QueryPlanner`, `RetrievalManager`, and `EvidenceFusion` in `AgentController`. Keep the old `self.router` and `self.supervisor` only behind a temporary compatibility flag if existing callers require them; the default path must use the new pipeline.

- [ ] **Step 4: Update answer context and confidence**

Pass only selected evidence to the prompt, grouped by subquestion. Deduplicate source display by `evidence_id`/document ID. Compute confidence from coverage, best relevance, authority, and conflict count. Trigger fallback on `EvidenceBundle.fallback_reason`, not only on an empty source list.

- [ ] **Step 5: Preserve SSE compatibility during migration**

Generate a request-scoped `trace_id`, emit the existing `router` event from the planner summary and the existing `supervisor` event from fusion summary, and include only `trace_id`, retriever names, counts, coverage, and fallback reason in the optional `meta.retrieval_summary`. Keep `meta`, `token`, and `done` unchanged. Do not expose user document content in diagnostics.

- [ ] **Step 6: Run API and stream tests**

Run: `python -m pytest backend/tests/test_chat_stream.py backend/tests/test_orchestrator_retrieval.py backend/tests/test_evidence_contract.py -q -p no:cacheprovider`

- [ ] **Step 7: Commit**

Commit: `git add backend/agents/controller.py backend/agents/answer_generator.py backend/rag/prompt_templates.py backend/api/chat.py backend/tests/test_chat_stream.py backend/tests/test_orchestrator_retrieval.py; git commit -m "refactor: route chat through retrieval fusion"`

---

### Task 6: 稳定知识库身份、切分配置和索引一致性

**Files:**
- Modify: `crawler/chunking.py`
- Modify: `crawler/build_kb.py`
- Modify: `backend/rag/vector_store.py`
- Create: `backend/tests/test_kb_alignment.py`
- Modify: `analytics/evaluation.py`
- Modify: `analytics/run_analysis.py`

**Interfaces:**
- Every campus record gets `doc_id`, `doc_version`, `chunk_index`, `parent_id`, `source_url`.
- Add `validate_index_alignment(cleaned_dir, metadata_dir) -> list[str]` for all source directories, not only employment.
- Evaluation cases use `expected_doc_ids: set[str]`; titles remain optional display labels.

- [ ] **Step 1: Write failing alignment tests**

```python
def test_alignment_reports_cleaned_file_without_metadata(tmp_path):
    (tmp_path / "cleaned").mkdir()
    (tmp_path / "metadata").mkdir()
    (tmp_path / "cleaned" / "doc-a.txt").write_text("正文", encoding="utf-8")
    assert validate_index_alignment(tmp_path / "cleaned", tmp_path / "metadata") == ["doc-a"]

def test_evaluation_case_uses_stable_doc_id():
    case = RAGCase(
        query="缓考申请表在哪里下载？",
        expected_doc_ids={"jwc/student-download"},
        category="教务资料",
    )
    assert case.expected_doc_ids == {"jwc/student-download"}
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m pytest backend/tests/test_kb_alignment.py -q -p no:cacheprovider`

- [ ] **Step 3: Add stable IDs and metadata/version checks**

Derive `doc_id` from source directory plus normalized metadata/source URL, not from a mutable display title. Preserve stable chunk IDs across rebuilds when the source content/version is unchanged.

- [ ] **Step 4: Add per-type chunk configuration**

Keep short-document handling and Parent-Child structure. Add explicit configuration keys for notice, admission, training-plan, and download-list documents; default to the current safe ranges in the design spec.

- [ ] **Step 5: Validate before rebuilding**

`build_kb.main()` must fail before deleting collections if any cleaned document lacks matching metadata or if metadata has no source identity. The validation output must list the first 20 mismatches and total count.

- [ ] **Step 6: Update evaluation and run alignment tests**

Run: `python -m pytest backend/tests/test_kb_alignment.py backend/tests/test_chunking.py -q -p no:cacheprovider`

Run the offline evaluator and report both stable-ID hit rate and normalized title hit rate for migration comparison.

- [ ] **Step 7: Commit**

Commit: `git add crawler/chunking.py crawler/build_kb.py backend/rag/vector_store.py backend/tests/test_kb_alignment.py analytics/evaluation.py analytics/run_analysis.py; git commit -m "feat: stabilize knowledge base identities"`

---

### Task 7: 更新前端兼容层并退役旧编排

**Files:**
- Modify: `frontend/src/chatStore.js`
- Modify: `frontend/src/embeddedChatStore.js`
- Modify: `frontend/src/pages/ChatPage.jsx`
- Modify: `frontend/src/components/EmbeddedChat.jsx`
- Create: `frontend/src/retrievalSummary.js`
- Create: `frontend/src/retrievalSummary.test.js`
- Modify: `frontend/package.json`
- Modify: `backend/agents/router.py`
- Delete after all tests pass: `backend/agents/supervisor.py`, `backend/agents/llm_router.py`
- Delete after all imports are removed: old `QuestionRouter` compatibility code in `backend/agents/router.py`
- Modify: `backend/tests/test_router.py`, `backend/tests/test_chat_stream.py`

**Interfaces:**
- Frontend continues rendering `meta.sources`, `meta.attachments`, `meta.tools_used`, `meta.confidence`.
- New optional `meta.retrieval_summary` may show selected retriever names and coverage; it must not contain document text.
- During the transition old `router/supervisor` event handlers remain harmless; after frontend migration they are removed together with backend emitters.

- [ ] **Step 1: Add frontend state tests for the new summary**

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeRetrievalMeta } from './retrievalSummary.js';

test('keeps source and attachment metadata when retrieval summary arrives', () => {
  const result = mergeRetrievalMeta(
    { sources: [{ title: '缓考申请表', url: '/file.pdf' }] },
    { retrieval_summary: { retrievers: ['download_search', 'campus_rag'], coverage: 1 } },
  );
  assert.equal(result.sources.length, 1);
  assert.equal(result.retrieval_summary.coverage, 1);
});
```

`retrievalSummary.js` exports `mergeRetrievalMeta(previous, incoming)`, implemented as a shallow metadata merge that preserves existing `sources`, `attachments`, `tools_used`, and `confidence` when the incoming event contains only `retrieval_summary`. Add this test file to the existing `frontend/package.json` test script.

- [ ] **Step 2: Run existing frontend tests before edits**

Run: `npm test -- --run`

Record the current result; do not treat unrelated pre-existing failures as caused by this task.

- [ ] **Step 3: Update stores and components**

Map the new `retrieval_summary` from `meta`, keep old event handlers during the migration, and remove UI labels that imply a global Supervisor priority.

- [ ] **Step 4: Remove old backend imports and compatibility fields**

Use `rg -n "EvidenceSupervisor|QuestionRouter|LLMRouter|evidence_priority|supervisor_reason|route_mode" backend frontend/src` and remove only references proven unused by tests. Keep response fields temporarily if external clients may use them; mark them deprecated in code comments.

- [ ] **Step 5: Run full backend and frontend verification**

Run: `python -m pytest backend/tests -q -p no:cacheprovider`

Run: `npm test -- --run`

Run: `npm run build`

- [ ] **Step 6: Commit**

Commit: `git add backend frontend; git commit -m "refactor: retire exclusive agent orchestration"`

---

### Task 8: 端到端黄金集、指标和最终验收

**Files:**
- Modify: `analytics/evaluation.py`
- Modify: `analytics/run_analysis.py`
- Create: `backend/tests/test_golden_retrieval.py`
- Modify: `docs/ZHKU_Campus_Agent_开发.md`

**Interfaces:**
- Each golden case includes query, expected stable IDs, expected subquestions, and whether fallback is acceptable.
- Evaluation output includes Recall@1/3/5/10, MRR, independent source count, coverage, citation correctness, fallback correctness, and latency.
- Update `RAGCase` to `RAGCase(query: str, expected_doc_ids: set[str], category: str, expected_titles: set[str] = field(default_factory=set))`; import `field` from `dataclasses`; stable IDs are canonical and titles are migration-only.

- [ ] **Step 1: Add the golden cases**

Include at least the following: 缓考申请表、学生证补办、学籍异动、网络报障电话、招生章程、专业目录、研究生调剂、校医院医保、多轮“那申请条件呢”、路线+天气复合问题。

- [ ] **Step 2: Add end-to-end assertions**

```python
import asyncio

def test_golden_download_case_reaches_correct_evidence(live_controller):
    result = asyncio.run(live_controller.handle("缓考申请表在哪里下载？"))
    titles = {source["title"] for source in result["sources"]}
    assert any("缓考" in title for title in titles)
    assert result["fallback"] is False
```

The test module defines the `live_controller` fixture by monkeypatching the
vector store, structured tools, and live API clients with deterministic local
fakes, then constructing `AgentController`; it performs no network or model
calls. The fixture returns the controller's normalized result object so the
same assertions exercise planner, retrieval manager, fusion, and citation
mapping together.

- [ ] **Step 3: Run the full verification matrix**

Run:

```powershell
python -m pytest backend/tests -q -p no:cacheprovider
python -m pytest analytics/tests/test_core.py analytics/tests/test_run_analysis.py -q -p no:cacheprovider
npm test -- --run
npm run build
```

Expected acceptance: official RAG Recall@5 >= 90%, key download/contact Top-3 >= 95%, no regression in SSE completion, and no user-document cross-tenant leakage.

- [ ] **Step 4: Inspect traces and document residual failures**

For every failed golden case, inspect planner output, raw candidates, filtered candidates, fused evidence, and citation mapping. Do not fix by adding a single query-specific keyword; fix the relevant contract or ranking stage.

- [ ] **Step 5: Commit final evaluation and documentation**

Commit: `git add analytics backend/tests docs/ZHKU_Campus_Agent_开发.md; git commit -m "test: add end-to-end retrieval acceptance suite"`

## Execution Notes

- Execute tasks in order. A task is complete only after its focused tests pass.
- If a task exposes an incompatible existing behavior, add a regression test and update the contract before changing the next task.
- Do not stage or commit unrelated existing worktree changes.
- Before claiming completion, run the verification commands in Task 8 and report any environment-limited tests separately.
