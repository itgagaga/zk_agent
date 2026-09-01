# 个人知识库检索可靠性统一改造计划

> 日期：2026-08-31  
> 状态：Task 0–6 已实施  
> 实施节奏：按 Task 顺序逐步开发；每个 Task 通过对应测试后再进入下一步。

## 1. 问题结论

“增强”模式已正确把 `user_docs` 加入检索计划，用户文档元数据和 13 个向量片段也都存在。
实际失败发生在个人文档首次命中后的完整文档扩展阶段：代码向 Chroma 传入了包含两个普通字段的
`where`，而当前 Chroma 要求多个条件使用 `$and`。

当前已确认的同类风险点：

- `RAGRetriever._enrich_user_doc_hits()` 调用 `count_documents()` 时传入
  `{"doc_id": ..., "user_id": ...}`。
- `VectorStore.get_chunks_by_doc_id()` 以逐项赋值方式构造相同的双字段过滤器。
- `VectorStore.query()`、`keyword_search()`、`delete_documents()`、`count_documents()`
  都直接信任调用方的 `where`，缺少统一规范化边界。
- `RetrievalManager` 使用 `return_exceptions=True` 保证其他检索器继续工作，但异常只进入内部
  `failed_retrievers`，最终用户无法区分“个人库没命中”和“个人库执行失败”。
- 现有 FakeStore 测试不校验 Chroma 过滤器语法，并且有测试断言固化了错误的双字段字典。

## 2. 统一目标

本轮不只修复一处 `$and`，而是建立四层统一约束：

1. 所有 Chroma metadata 过滤条件由一个入口规范化。
2. 所有检索器统一产出 `成功 / 无命中 / 失败 / 跳过` 状态。
3. “增强”和“私有”模式对个人库失败采用明确且不同的降级策略。
4. 日志、SSE 和前端明确展示个人资料是否尝试、命中、采用或失败。

任何诊断均不得输出个人文档正文、片段内容或原始异常中的敏感参数。

## 3. 状态语义

保留现有字段，并新增稳定状态，避免三个布尔值无法表达失败原因。

```text
personal_documents_requested   是否选择增强/私有模式
personal_documents_available   数据库是否登记了当前用户文档
personal_documents_attempted   是否实际启动 user_docs 检索
personal_documents_hit         是否召回至少一条合格候选
personal_documents_used        最终回答证据是否保留个人片段
personal_documents_status      not_requested / empty_library / retrieved /
                               no_hit / failed
```

`available=true, used=false` 不再是唯一信息；前端可以通过 `status` 区分“正常无命中”和“执行失败”。

## 4. 分步实施任务

## Task 0：先建立真实失败测试（已完成）

**Files:**

- Create: `backend/tests/test_vector_store_filters.py`
- Modify: `backend/tests/test_rag_retriever_precision.py`
- Modify: `backend/tests/test_scope_diagnostics.py`

**内容：**

- 使用严格 FakeCollection 模拟 Chroma：根级多个普通字段直接报错。
- 复现 `user_id + doc_id` 的 count、完整文档拉取、parent 拉取路径。
- 复现“增强模式中 user_docs 报错但公共检索成功”的静默降级。
- 复现“私有模式中 user_docs 报错”不得产生公共答案。
- 修改现有错误断言，要求多条件最终表现为 `$and`。

**验收：** 新测试在生产代码修改前稳定失败，不调用外部 LLM/API。

## Task 1：统一 Chroma 过滤器边界（已完成）

**Files:**

- Modify: `backend/rag/vector_store.py`
- Modify: `backend/rag/retriever.py`
- Modify: `backend/tests/test_vector_store_filters.py`

**内容：**

- 在 `VectorStore` 增加唯一的 metadata filter 组合/规范化函数。
- 单条件保持 `{"user_id": 2}`；多个条件统一转为
  `{"$and": [{"user_id": 2}, {"doc_id": "..."}]}`。
- 已存在的 `$and` 条件安全展开或原样保留，禁止产生嵌套歧义。
- `query`、`keyword_search`、`delete_documents`、`count_documents`、
  `get_chunks_by_parent_id`、`get_chunks_by_doc_id` 在调用 Chroma 前统一规范化。
- Retriever 不再自行拼接未经校验的多字段字典。

**验收：** 所有向量库入口接受同一种调用方式，严格 FakeCollection 测试全部通过。

## Task 2：统一检索器执行结果（已完成）

**Files:**

- Modify: `backend/rag/contracts.py`
- Modify: `backend/rag/retrieval_manager.py`
- Modify: `backend/tests/test_scope_diagnostics.py`
- Modify: `backend/tests/test_targeted_retrieval_retry.py`

**内容：**

- 每个有效 retriever 记录统一状态：`success / empty / error / skipped`。
- 异常记录 retriever 名、异常类型、阶段和 `trace_id`，不记录查询正文和文档内容。
- `candidate_counts`、`failed_retrievers`、`retrieval_errors` 从同一执行结果生成，避免互相覆盖。
- 新增 `personal_documents_attempted`、`personal_documents_hit` 和
  `personal_documents_status`；现有 requested/available/used 从统一结果推导。
- 重试保持资料范围约束，并保留首次失败信息。

**验收：** `retrieval_summary` 能准确区分未请求、空库、无命中、命中未采用、已采用和执行失败。

## Task 3：统一模式降级策略（已完成）

**Files:**

- Modify: `backend/agents/controller.py`
- Modify: `backend/agents/fallback.py`
- Modify: `backend/rag/evidence_gate.py`（如现有 partial 规则不足）
- Create/Modify: controller 和个人资料模式测试

**行为：**

| 模式 | `user_docs` 无命中 | `user_docs` 执行失败 |
|---|---|---|
| 标准 | 不适用 | 不适用 |
| 增强 | 使用标准资料正常回答，状态为 `no_hit` | 使用标准资料回答，但明确提示“个人资料检索失败，本回答仅基于标准资料” |
| 私有 | 明确提示个人资料未覆盖 | 明确提示个人资料检索失败，不得改用任何公共资料或工具 |

**验收：** 任何个人库失败都不会伪装成“已正常结合个人资料”。

## Task 4：前端展示检索状态（已完成）

**Files:**

- Modify: `frontend/src/chatStore.js`
- Modify: `frontend/src/retrievalSummary.js`
- Modify: `frontend/src/pages/ChatPage.jsx`
- Modify: `frontend/src/styles.css`
- Modify: frontend tests

**内容：**

- 在回答元信息附近展示简短状态：`已使用个人资料`、`个人资料未命中`、
  `个人资料检索失败`。
- 失败使用警示色；正常命中沿用“增强”橙色；私有模式沿用紫色。
- 不展示私有文档正文、内部异常和用户 ID。
- 标准模式不增加无意义状态提示。

**验收：** 用户无需查看后端日志即可知道本次回答是否真正使用了个人知识库。

## Task 5：结构化日志与开发文档（已完成）

**Files:**

- Modify: `backend/rag/retrieval_manager.py`
- Modify: `docs/ZHKU_Campus_Agent_开发.md`
- Modify: `docs/personal-knowledge-scope.puml`

**内容：**

- 按 `trace_id / retriever / status / candidate_count / error_type` 输出结构化诊断。
- 日志禁止输出私有片段、文档正文和完整用户查询。
- 更新三种模式的成功、无命中和失败流程图。

**验收：** 一条请求可以通过 `trace_id` 还原每个检索器的执行结果。

## Task 6：完整回归与真实冒烟验证（已完成）

**内容：**

- 运行后端全量测试、前端测试和生产构建。
- 使用当前用户真实培养方案验证：
  - 标准模式不调用 `user_docs`；
  - 增强模式对“我是信计大一学生，有什么建议”能够命中并保留培养方案证据；
  - 私有模式只调用 `user_docs`；
  - 人为制造个人检索异常时，增强/私有模式按 Task 3 明确提示。
- 核对 SSE `router`、`retrieval`、`meta` 三阶段状态一致。

**本轮结果：** 后端全量测试 161 passed；前端测试 10 passed；生产构建成功；当前用户
`user_id=2` 的信计问题真实个人检索召回 13 个个人知识库片段。标准/增强/私有的调用边界、
失败兜底和 SSE 诊断由后端与前端测试覆盖。

**最终验收：** Planner 声明、实际调用、检索结果、最终引用和前端提示五层状态一致，
不再出现“日志里有 `user_docs`，回答却静默忽略个人资料”的情况。

## 5. 实施结果

Task 0–6 已全部完成。后续如继续优化，建议另开性能或可观测性专项，不再修改本轮可靠性验收范围。
