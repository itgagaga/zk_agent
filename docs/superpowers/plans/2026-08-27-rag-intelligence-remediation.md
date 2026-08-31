# RAG 查询理解与证据裁决智能化修复实施计划

> 本计划以 2026-08-27 当前代码为基线，修复“规则路由看起来像智能 Agent，但 LLM 只参与最终答案生成”的问题。
>
> 本计划补充并修正 `2026-08-19-rag-orchestration-simplification.md` 中已经实施、但未达到预期的 Query Planner、混合检索和 Evidence Gate 部分。实施时以本文为准，不重复推翻已经稳定的 SSE、证据契约和用户隔离机制。

**目标：** 让系统在查询理解、上下文补全、问题分解、检索器选择、中文混合召回和证据充分性判断上具备可验证的语义能力，同时保留确定性降级路径。

**核心原则：** LLM 负责语义理解和结构化决策，但不能直接绕过权限、检索范围或证据校验；规则只作为安全约束与不可用时的保守降级，不再作为主要“智能”来源。

**实施方式：** 按任务逐步落地。每个任务先添加失败测试，再修改实现；每一步完成后项目必须保持可运行。不要一次性重写全部 RAG 文件。

---

## 1. 当前已确认问题

### 1.1 工具选择依赖固定关键词

当前 `backend/rag/query_planner.py` 通过 `_TOOL_RULES` 做字符串包含判断。常见口语表达无法触发正确工具，例如：

| 用户表达 | 应使用 | 当前实际 |
|---|---|---|
| 今天要不要带伞？ | `weather_search` | `campus_rag` |
| 广州南站坐地铁去白云校区 | `map_route` | `campus_rag` |
| 最近有什么招聘会？ | `job_search` | `campus_rag` |
| 学校最近有什么通知？ | `news_search` | `campus_rag` |
| 网络坏了找谁？ | `contact_search` / `service_link_search` | `campus_rag` |

### 1.2 没有独立查询改写

`normalize()` 只删除空格和末尾标点。普通 RAG 不会利用历史补齐省略实体：

```text
上一轮：白云校区网络报障电话是多少？
当前轮：那海珠校区呢？
```

当前检索词仍是“那海珠校区呢”，而不是“海珠校区网络报障电话”。

### 1.3 问题分解只有数据结构

虽然存在 `SubQuestion`，每次仍固定生成一个 `q1`。复合问题没有拆成可分别检索、分别验收的子问题。

### 1.4 登录后无条件检索私有文档

当前条件为 `user_id is not None` 即加入 `user_docs`。天气、路线、电话等问题也会混入个人培养方案或其他上传文档。

### 1.5 词法检索是字符滑窗

当前以 2～6 字连续片段做 OR 匹配，并通过“章程 +15、简章 -10”等手工规则排序。这不是中文分词/BM25，也无法自然处理同义表达。

### 1.6 Evidence Gate 依赖固定概念表

Gate 只认识少量 `_ALIASES`。未识别到概念时，只要存在任意证据就返回 `sufficient/1.0`；补检索后仍为 `needs_more` 时，Controller 仍然继续生成答案。

### 1.7 相关附带问题

- `AGENT_ROUTER_MODE=hybrid/llm` 不影响当前主 Controller；旧 `LLMRouter` 不在运行链路中。
- 共享 `document` 集合未进入主聊天检索计划。
- dense、字符匹配、工具结果的原始分数范围不同，却直接参与全局排序。
- 没有二阶段语义 reranker。
- 置信度只按来源数量计算。
- 当前黄金测试主要验证包含固定关键词的问法，不能衡量语义泛化。

---

## 2. 目标架构

```text
当前问题 + 最近对话 + 页面上下文
        ↓
Hybrid Query Planner
  - LLM Structured Output：意图、实体、独立查询、子问题、检索目标
  - 确定性校验：工具白名单、权限、数量和长度限制
  - 保守规则降级：LLM 不可用时仍可工作
        ↓
Retrieval Manager（按子问题并行）
  - campus_rag
  - shared_docs
  - user_docs（仅显式需要时）
  - download/contact/service/major/job/news
  - weather/map/academic
        ↓
Hybrid Retrieval
  - dense embedding
  - 中文分词 + BM25
  - 结构化字段检索
        ↓
Rank Fusion + Semantic Reranker
  - RRF 统一不同召回器排名
  - doc/parent 去重
  - Cross-Encoder 可选重排
        ↓
Evidence Judge
  - 每个子问题：supported / partial / unsupported
  - 引用哪些 evidence_id
  - 缺少什么信息、是否冲突
        ↓
充分：生成带引用答案
部分充分：只回答已支持部分并说明缺口
不充分：改写补检索一次，仍失败则拒答
```

---

## 3. 全局约束与非目标

### 3.1 必须保持

- 保持现有 `/api/chat` 和 `/api/chat/stream` 请求入口。
- 保持 SSE `router/retrieval/meta/token/done` 基本事件顺序；允许在事件中增加可选字段。
- 用户私有文档所有实际检索必须带 `user_id` 过滤。
- LLM 输出只能选择服务端白名单内的检索器，不能决定任意函数名或过滤其他用户数据。
- LLM、reranker 或 BM25 不可用时必须可降级，不得导致所有校园问答不可用。
- 不通过不断增加关键词特例、无限提高 Top-K 或只改 Prompt 掩盖问题。

### 3.2 本轮不做

- 不更换 Chroma。
- 不引入新的 Agent 框架。
- 不重写前端聊天页面。
- 不在本计划中修复 DOC/OCR、课表、简历等非 RAG 问题。
- 不把开放域常识回答加入校园 Agent；没有校园证据时仍应明确拒答。

---

## 4. 新的数据契约

修改 `backend/rag/query_planner.py` 和 `backend/rag/contracts.py`，建立下面的稳定契约。

### 4.1 RetrievalTarget

```python
RetrievalTarget = Literal[
    "campus_rag",
    "shared_docs",
    "user_docs",
    "download_search",
    "contact_search",
    "service_link_search",
    "major_search",
    "job_search",
    "news_search",
    "weather_search",
    "map_route",
    "academic_search",
]
```

### 4.2 SubQuestion

```python
class SubQuestion(BaseModel):
    id: str
    query: str
    intent: str
    retrievers: list[RetrievalTarget]
    entities: dict[str, str] = Field(default_factory=dict)
    filters: dict[str, str | int | bool] = Field(default_factory=dict)
    requires_private_context: bool = False
```

### 4.3 RetrievalPlan

```python
class RetrievalPlan(BaseModel):
    original_query: str
    standalone_query: str
    language: str = "zh"
    subquestions: list[SubQuestion]
    retrievers: list[RetrievalTarget]
    used_history: bool = False
    planner_source: Literal["llm", "rule_fallback"]
    planner_reason: str = ""
    trace_id: str
```

### 4.4 EvidenceAssessment

```python
class SubQuestionAssessment(BaseModel):
    subquestion_id: str
    status: Literal["supported", "partial", "unsupported"]
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    reason: str = ""

class EvidenceAssessment(BaseModel):
    status: Literal["supported", "partial", "unsupported"]
    subquestions: list[SubQuestionAssessment]
    should_retry: bool = False
    retry_query: str | None = None
```

不得继续用单个 `coverage: float` 表示所有问题是否得到回答。覆盖状态必须关联具体子问题。

---

## 5. 分阶段实施任务

## Task 0：建立真实失败基线

**目标：** 先证明当前规则在同义表达、多轮追问和无关证据上失败，避免修复后仍只测演示问法。

**Files:**

- Create: `backend/tests/fixtures/rag_semantic_cases.json`
- Create: `backend/tests/test_query_understanding_regressions.py`
- Create: `backend/tests/test_evidence_gate_regressions.py`
- Modify: `analytics/evaluation.py`

### 测试集至少包含

1. 每个工具 8～12 种表达，其中至少一半不含旧规则关键词。
2. 正例和容易误触发的负例：
   - “天气很好”不一定表示要查询实时天气；
   - “下载速度慢”不能触发资料下载；
   - “我的专业”不等于“我的文档”。
3. 多轮省略：那海珠呢、条件呢、怎么下载、明天呢。
4. 多意图：路线 + 天气、材料 + 电话 + 入口。
5. 无答案问题与相似错误证据。
6. 登录用户有私有文档但问题与文档无关。

### 基线指标

- Retriever selection micro-F1。
- Standalone query entity preservation rate。
- Subquestion exact/semantic coverage。
- Private document false-positive rate。
- Evidence gate precision、recall、false-supported rate。
- Retrieval Recall@5、MRR、nDCG@5。

### 验收

- 测试能稳定复现当前至少六类已知失败。
- Fixture 不依赖外部 LLM/API，CI 可离线运行。
- 在线 LLM 评测单独标记 `integration`，不进入默认单元测试。

---

## Task 1：实现真正的 Hybrid Query Planner

**目标：** 用一次结构化 LLM 调用完成上下文补全、意图识别、实体抽取和子问题分解；失败时使用保守规则降级。

**Files:**

- Modify: `backend/rag/query_planner.py`
- Modify: `backend/rag/contracts.py`
- Modify: `backend/config.py`
- Modify: `backend/agents/controller.py`
- Create: `backend/tests/test_hybrid_query_planner.py`

### 接口变化

```python
async def plan(
    self,
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
    user_id: int | None = None,
    context_hint: str | None = None,
) -> RetrievalPlan:
    ...
```

Controller 中同步调用改为：

```python
plan = await self.planner.plan(
    question,
    history=history,
    user_id=user_id,
    context_hint=context_hint,
)
```

### LLM Structured Output 要求

单次输出必须包含：

- `standalone_query`：结合历史后可独立检索的问题；
- `subquestions`：1～5 个，不允许无限分解；
- 每个子问题的 `intent/retrievers/entities/filters`；
- 是否显式需要用户私有文档；
- 简短可审计的 `planner_reason`。

### 约束校验

- 检索器必须来自 `RetrievalTarget` 白名单。
- 无法确定时至少保留 `campus_rag`，但不能无条件加入所有工具。
- 未登录时强制移除 `user_docs`。
- `user_docs` 只有在以下任一条件成立时允许加入：
  - 用户明确说“我的文档、我上传的、这份文件、根据培养方案”等；
  - `context_hint` 明确表示当前页面正在围绕私有知识库；
  - 最近对话中已建立当前私有文档对象，当前轮是对其追问。
- 路线、天气等纯实时问题不默认加入 `campus_rag`。
- 每个子问题最多 4 个检索器，总子问题最多 5 个。

### 降级策略

删除当前大量业务关键词作为主逻辑，只保留最小保守规则：

- 明确 URL/电话/天气/路线等高精度词可直接选择对应工具；
- 其他问题默认 `campus_rag`；
- 不确定是否使用私有文档时默认不使用；
- 降级结果必须标记 `planner_source="rule_fallback"`。

### 必测用例

```python
"今天要不要带伞" -> weather_search
"广州南站坐地铁去白云校区" -> map_route
"网络坏了找谁" -> contact_search + service_link_search
"最近有什么招聘会" -> job_search
"学校最近发了什么通知" -> news_search
"那海珠校区呢" + 历史网络报障 -> standalone_query 包含海珠、网络报障、电话
"校园卡丢了，材料、地点、电话分别是什么" -> 至少 3 个子问题
```

### 验收

- 语义表达选择准确率达到测试集 90% 以上。
- 多轮实体保留率达到 95% 以上。
- Planner 只调用一次 LLM，不为每个子问题重复调用。
- LLM 不可用时保守降级测试全部通过。

---

## Task 2：按意图选择共享文档和私有文档

**目标：** 修复“登录即搜索私有文档”，并让共享文档集合真正进入主问答。

**Files:**

- Modify: `backend/rag/retrieval_manager.py`
- Modify: `backend/rag/retriever.py`
- Modify: `backend/api/chat.py`
- Modify: `frontend/src/chatStore.js`
- Modify: `frontend/src/embeddedChatStore.js`
- Create: `backend/tests/test_document_retrieval_scope.py`

### 实施内容

1. 将文档检索拆成明确接口：

```python
search_shared_documents(query, top_k, filters)
search_user_documents(query, user_id, top_k, filters)
```

不要再通过 `user_id is None` 隐式切换两个完全不同的集合。

2. Retrieval Manager 按每个 `SubQuestion.retrievers` 调用集合。
3. `shared_docs` 映射到 `document` collection。
4. `user_docs` 必须显式携带当前用户 ID。
5. 将前端已经发送的 `context_hint` 加入 `ChatRequest`，用于说明嵌入式问答所在页面；它只能帮助选库，不能绕过用户过滤。
6. 普通校园问答默认不搜索 `user_docs`。

### 必测用例

- 登录用户问天气，不调用用户文档。
- 登录用户问“我的培养方案要求多少学分”，只检索自己的文档。
- 未登录用户说“我的文档”，Planner 移除 `user_docs` 并返回需要登录的明确状态。
- 共享招生章程能够由 `shared_docs` 检索到。
- 相同 `doc_id` 的其他用户片段永远不会进入 Parent 扩展结果。

### 验收

- 私有文档误触发率低于 2%。
- 共享文档黄金集 Recall@5 不低于 90%。
- 所有用户隔离回归测试通过。

---

## Task 3：用中文 BM25 替换字符滑窗匹配

**目标：** 删除 2～6 字符滑窗和业务特例加减分，建立真正的中文词法召回。

**Files:**

- Modify: `requirements.txt`
- Modify: `pyproject.toml`
- Create: `backend/rag/lexical_index.py`
- Modify: `backend/rag/vector_store.py`
- Modify: `backend/rag/retriever.py`
- Modify: `backend/tools/base.py`
- Create: `backend/tests/test_chinese_lexical_retrieval.py`

### 建议依赖

```text
jieba>=0.42.1
rank-bm25>=0.2.2
```

若不希望引入 `rank-bm25`，可以自行实现 BM25 公式，但不能退回字符 n-gram OR 匹配。

### LexicalIndex 设计

- 按 collection 建立内存 BM25 索引。
- 文档字段权重：标题 > 章节 > 部门/标签 > 正文。
- 中文使用 `jieba` 分词；英文和数字保留完整 token。
- 支持领域词典：校区名、部门名、专业名、常见业务名。
- 同义词不在 BM25 层写大量 `if`；由 Planner 输出查询扩展词，或由小型可配置同义词表提供有限规范化。
- upsert/delete/rebuild 后显式失效并重建对应 collection 索引。

### 删除内容

- 删除 `vector_store.keyword_search()` 中 2～6 字符滑窗。
- 删除“章程 +15、简章 -10、学校概况 +8、本科命中研究生 -8”等业务特例。
- 删除 `BaseTool._extract_keywords()` 的连续 2 字切片。

### 结构化工具

结构化工具优先使用 Planner 提取的实体和过滤字段：

- `department`
- `campus`
- `year`
- `document_type`
- `major_name`
- `service_name`

只有缺少结构化实体时，才使用 BM25 对标题/摘要排序。

### 验收

- 同义改写后的 Recall@10 明显高于当前字符滑窗基线。
- 通用词“下载、学校、申请、怎么”不能单独把无关条目排到前列。
- 不再存在针对某一个演示问题的固定加减分代码。
- 词法索引结果可返回 `lexical_rank` 和 `bm25_score` 供诊断，但不直接与 cosine score 相加。

---

## Task 4：统一不同召回器的排名融合

**目标：** 避免 dense、BM25、工具分数跨量纲直接比较。

**Files:**

- Modify: `backend/rag/contracts.py`
- Modify: `backend/rag/evidence_fusion.py`
- Modify: `backend/rag/retriever.py`
- Create: `backend/tests/test_rank_fusion.py`

### Evidence 增加字段

```python
dense_rank: int | None = None
lexical_rank: int | None = None
tool_rank: int | None = None
rerank_score: float | None = None
fusion_score: float = 0.0
```

原始分数可以保留用于诊断，但不能再作为跨来源全局排序的唯一依据。

### 第一阶段：RRF

```python
rrf_score = sum(1 / (k + rank) for rank in available_ranks)
```

- 初始 `k=60`，通过离线评测调整。
- 按 `doc_id + parent_id` 去重。
- 每个子问题单独融合。
- 同一文档多个 Chunk 不计作多个独立来源。
- 工具结果也通过 rank 进入融合，而不是把 `match_score=20` 与 cosine 直接比较。

### 第二阶段：可选语义 reranker

增加配置：

```env
RAG_RERANKER_ENABLED=true
RAG_RERANKER_MODEL=BAAI/bge-reranker-base
RAG_RERANKER_TOP_N=20
```

仅对 RRF 后的前 20 条执行 Cross-Encoder，最终每个子问题保留 5～8 条。若模型不可用，继续使用 RRF。

### 验收

- dense 与 BM25 任一召回到正确文档时，正确文档应进入最终 Top-5。
- 单个召回器的异常高原始分数不能压制其他来源。
- 同一 Parent 的多个 Child 不得占满最终上下文。
- RRF 与 reranker 都有离线可复现测试。

---

## Task 5：重写 Evidence Gate 为子问题级 Evidence Judge

**目标：** 不再用固定概念表决定“是否能回答”，而是判断证据是否支持每个子问题。

**Files:**

- Modify: `backend/rag/evidence_gate.py`
- Modify: `backend/rag/contracts.py`
- Modify: `backend/rag/retrieval_manager.py`
- Modify: `backend/agents/controller.py`
- Create: `backend/tests/test_evidence_judge.py`

### 两层判断

#### 第一层：确定性预检查

- 没有证据：`unsupported`。
- reranker/RRF 分数低于最低门槛：`unsupported`。
- 子问题没有任何分配证据：该子问题 `unsupported`。
- API/工具明确报错：记录为检索失败，不伪装成“没有公开资料”。
- 同一来源重复 Chunk 不增加独立支持度。

#### 第二层：LLM Structured Evidence Judge

输入：子问题、候选证据的 `evidence_id/title/snippet/source/date`。

输出必须符合 `EvidenceAssessment`，并回答：

- 哪些证据直接支持问题；
- 是否只支持部分内容；
- 缺少哪些信息；
- 是否存在年份、适用对象或政策冲突；
- 是否值得进行一次查询改写重试。

LLM 不得生成答案，只做证据分类；temperature=0。

### 保守降级

Judge 不可用时：

- 不再采用“未识别概念 + 任意证据 = sufficient”。
- 使用 reranker 阈值、实体覆盖和子问题分配做保守判断。
- 无法确认时返回 `partial`，不能自动升级为 `supported`。

### Controller 行为

```python
supported   -> 正常回答
partial     -> 只回答有证据部分，并明确列出未覆盖项
unsupported -> fallback
```

补检索一次后仍为 `partial/unsupported`，不得继续假装完整回答。

### 必测用例

- “校园卡丢了怎么办” + 泛化校园介绍：不得 `supported`。
- “本科招生章程” + 研究生章程：不得 `supported`。
- “那海珠校区呢” + 只有白云校区证据：不得 `supported`。
- 三个子问题只覆盖两个：整体为 `partial`。
- 同一文档五个 Chunk：独立来源数仍为 1。

### 验收

- false-supported rate 低于 5%。
- 无答案问题拒答准确率不低于 90%。
- `needs_more` 旧状态被删除或完整迁移，不再出现诊断为不足却继续完整回答的路径。

---

## Task 6：实现一次有目的的查询重试

**目标：** 将当前“原查询 Top-K 扩大到 20”改成基于缺失信息的查询改写。

**Files:**

- Modify: `backend/rag/retrieval_manager.py`
- Modify: `backend/rag/query_planner.py`
- Modify: `backend/rag/evidence_gate.py`
- Create: `backend/tests/test_targeted_retrieval_retry.py`

### 重试条件

- 仅 `EvidenceAssessment.should_retry=True` 时执行。
- 每个请求最多一次，防止循环。
- 重试使用 Judge 给出的 `retry_query` 或 Planner 基于 `missing_information` 生成的新查询。
- 可以调整检索目标，例如第一次误搜官网，第二次补搜共享文档或结构化工具。
- 合并第一次和第二次证据后重新执行融合与 Judge。

### 禁止行为

- 不允许只是把同一句查询的 Top-K 从 5 调到 20。
- 不允许无限递归。
- 不允许在用户未授权的情况下补搜私有文档。

### 验收

- “本科招生章程”首次命中研究生章程时，重试查询能保留年份和本科适用对象。
- 多轮追问重试不能丢失历史实体。
- 重试前后 trace 中能看到 query 和检索目标变化。

---

## Task 7：按证据状态生成答案和置信度

**目标：** 让最终 LLM 只看到通过 Judge 的证据，并使置信度与证据质量一致。

**Files:**

- Modify: `backend/agents/answer_generator.py`
- Modify: `backend/rag/prompt_templates.py`
- Modify: `backend/agents/controller.py`
- Modify: `backend/api/chat.py`
- Create: `backend/tests/test_grounded_answer_generation.py`

### 修改内容

1. 不再给所有请求固定 `evidence_mode="composite"`。
2. 按 Plan 生成模式：`rag/document/tool/api/composite`。
3. 只把 `supporting_evidence_ids` 对应证据放入该子问题的上下文。
4. `partial` 必须在 Prompt 中明确要求只回答已支持部分。
5. 引用按 `evidence_id` 与结论绑定，不能只在文末罗列所有候选来源。

### 置信度建议

置信度由以下因素组合：

- 所有子问题是否 supported；
- 最低 reranker/fusion score；
- 独立文档数量；
- 是否存在未解决冲突；
- 是否发生降级 Planner/Judge；
- 是否使用实时 API 且 API 成功。

禁止继续使用“来源数量大于等于 2 即 high”。

### 验收

- 无关证据不会出现在 Prompt。
- 部分回答不会伪装成完整回答。
- 来源卡片只展示实际支持答案的证据。
- 单一权威来源可以是高置信度，多条低相关来源不能自动成为高置信度。

---

## Task 8：清理旧路由和配置歧义

**目标：** 避免仓库同时存在“看起来启用但实际不运行”的两套智能路由。

**Files:**

- Modify: `backend/config.py`
- Delete after migration: `backend/agents/llm_router.py`
- Delete or reduce to compatibility adapter: `backend/agents/router.py`
- Modify: tests and PlantUML diagrams
- Modify: `.env.example`
- Modify: `docs/ZHKU_Campus_Agent_开发.md`

### 配置建议

```env
QUERY_PLANNER_MODE=hybrid       # hybrid | llm | rule_fallback
QUERY_PLANNER_MODEL=deepseek-chat
EVIDENCE_JUDGE_ENABLED=true
RAG_LEXICAL_MODE=bm25
RAG_RERANKER_ENABLED=true
RAG_MAX_SUBQUESTIONS=5
RAG_MAX_RETRY=1
```

迁移完成后废弃 `AGENT_ROUTER_MODE`，避免用户以为修改它会影响主链路。

### 验收

- 生产代码中只有一条 Query Planner 入口。
- 文档、配置和实际运行链路一致。
- 不再存在仅由测试调用、却被文档描述为生产功能的 LLM Router。

---

## Task 9：建立语义 RAG 验收集

**目标：** 确保以后不会再次为了通过少量演示问题而堆叠关键词特例。

**Files:**

- Create: `analytics/rag_semantic_evaluation.py`
- Create: `analytics/fixtures/rag_semantic_gold.json`
- Modify: `analytics/run_analysis.py`
- Create: `backend/tests/test_semantic_gold_schema.py`

### 每个黄金问题字段

```json
{
  "id": "weather-paraphrase-01",
  "question": "今天出门需要带伞吗？",
  "history": [],
  "expected_retrievers": ["weather_search"],
  "forbidden_retrievers": ["user_docs"],
  "expected_entities": {"date": "today"},
  "expected_doc_ids": [],
  "expected_gate": "supported"
}
```

### 数据集组成

- 30% 直接表达。
- 30% 同义/口语改写。
- 15% 多轮追问。
- 15% 多意图问题。
- 10% 无答案或容易误判的问题。

每个业务意图至少 20 条，不能只有 1～2 个演示句。

### 上线门槛

- Retriever selection micro-F1 ≥ 0.90。
- Private-doc false-positive rate ≤ 0.02。
- Standalone query entity preservation ≥ 0.95。
- Evidence false-supported rate ≤ 0.05。
- 官网/文档 Recall@5 ≥ 0.90。
- 引用支持率 ≥ 0.95。
- 对旧黄金集不得出现超过 2% 的明显回归。

---

## 6. 推荐实施顺序

```text
Task 0 失败基线
  ↓
Task 1 Hybrid Planner + 查询改写 + 问题分解
  ↓
Task 2 文档检索范围修复
  ↓
Task 3 中文 BM25
  ↓
Task 4 RRF / Reranker
  ↓
Task 5 Evidence Judge
  ↓
Task 6 定向补检索
  ↓
Task 7 Grounded Answer / Confidence
  ↓
Task 8 清理旧路由
  ↓
Task 9 完整语义验收
```

Task 1 和 Task 2 完成后，用户最明显的“工具选错、追问听不懂、私有文档乱入”问题应得到改善。

Task 3～Task 5 完成后，RAG 才能从“命中几个字符就回答”升级到“语义召回、统一排序、证据不足不回答”。

---

## 7. 分阶段开关与回退

实施期间保留功能开关：

```env
QUERY_PLANNER_MODE=rule_fallback|hybrid
RAG_LEXICAL_MODE=legacy|bm25
RAG_FUSION_MODE=legacy|rrf
EVIDENCE_JUDGE_ENABLED=false|true
RAG_RERANKER_ENABLED=false|true
```

要求：

- 每个开关只保留一个版本周期，验收后删除旧路径，避免长期双实现。
- 回退只回退当前阶段，不回退用户数据或知识库内容。
- 新旧路径使用同一黄金集比较，不凭主观体验切换。

---

## 8. 可观测性要求

每个请求通过 `trace_id` 记录：

- 原始问题、独立查询；
- Planner 来源和选择原因；
- 子问题及其检索器；
- 是否使用历史、共享文档、私有文档；
- 每个检索器候选数量；
- dense/BM25 原始排名与 RRF 排名；
- reranker 分数；
- 每个子问题的 Gate 结果；
- 重试查询和触发原因；
- 最终被引用与被淘汰的 evidence ID。

不要记录用户私有文档全文；诊断日志只保留 ID、标题、分数和有限长度摘要。

---

## 9. 完成定义

以下条件全部满足，才能认为这轮 RAG 智能化修复完成：

1. 主 Controller 确实调用 Hybrid/LLM Query Planner，而非只调用关键词表。
2. 常见同义表达能选择正确工具，不要求用户说出固定词。
3. 多轮追问会生成包含上一轮核心实体的独立查询。
4. 复合问题会拆成多个可分别检索和验收的子问题。
5. 登录不再自动触发私有文档，只有明确文档意图才检索。
6. 共享 `document` 集合进入主问答链路。
7. 字符滑窗和问题特例加减分从主检索路径移除。
8. dense、BM25、工具结果通过 RRF/统一 reranker 融合。
9. Gate 不再依赖有限概念表，也不再把未知问题自动判为充分。
10. `partial/unsupported` 能真正限制最终生成，而非只作为诊断字段。
11. 置信度不再只取决于来源数量。
12. 语义改写、多轮、无答案和私有文档负例达到 Task 9 的上线门槛。

---

## 10. 首个开发迭代建议

第一迭代只实施 Task 0～Task 2，控制改动范围：

1. 新增语义失败测试集。
2. 将 Query Planner 改为异步 Hybrid Planner。
3. 一次 LLM Structured Output 完成查询改写、意图识别和子问题分解。
4. Controller 传入历史与 `context_hint`。
5. 明确拆分 `shared_docs` 与 `user_docs`。
6. 修复登录用户无条件检索私有文档。

第一迭代验收后再进入 BM25、RRF 和 Evidence Judge。这样可以先解决用户最明显的“不理解自然表达”问题，同时避免一次性同时改动规划、召回、排序和生成而难以定位回归。
