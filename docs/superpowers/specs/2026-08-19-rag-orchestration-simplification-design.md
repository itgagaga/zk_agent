# RAG 与多 Agent 编排简化设计

**日期：** 2026-08-19  
**状态：** 待用户评审  
**范围：** `backend/agents`、`backend/rag`、结构化检索工具、知识库构建与评测

## 1. 背景

当前问答链路由规则 Router、多个工具、RAG、文档检索、Supervisor 和 AnswerGenerator 组成。现状并非真正的自治多 Agent，而是“规则选路 + 工具调用 + 全局证据优先级”。这种结构带来四类问题：

1. Router 把意图识别变成排他执行开关，选中工具后可能完全不调用 RAG。
2. Supervisor 根据来源类型和结果是否非空裁决，而不校验证据相关性与问题覆盖度。
3. 结构化工具宽松匹配且缺少排序，错误但非空的结果会压制正确 RAG 证据。
4. RAG 在过滤、Parent 合并和去重前截断候选，重复片段占据 Top-K 且不补位。

已复现的代表性问题是“缓考申请表在哪里下载”：下载工具返回 43 条，正确项目排第 19 并被默认 Top-10 截断；直接 RAG 的第 1 条已经包含正确答案，但由于 fast 工具路径未调用 RAG，最终答案无法取得这条证据。

## 2. 目标

本次重构以“正确证据可达、行为可解释、组件可独立测试”为第一目标：

- 删除全局来源优先级和排他式路由。
- 用单一 Orchestrator 驱动查询理解、检索、证据融合与生成。
- 普通校园问题默认保留官网 RAG 作为基础证据源。
- 结构化工具返回可比较、可排序、可解释的证据。
- RAG 支持混合召回、按文档去重、Parent 扩展和候选补位。
- 最终置信度基于证据质量与覆盖度，而不是来源数量。
- 建立从问题到最终引用的端到端回归评测。

## 3. 非目标

- 本次不引入 LangGraph 或新的 Agent 框架。
- 不增加新的外部向量数据库。
- 不以更大的 Top-K、调整 Prompt 或降低阈值作为主要修复。
- 不在第一阶段引入额外 LLM reranker；先使用可复现的确定性融合。
- 不改变聊天 API 的核心响应字段和前端 `meta/token/done` SSE 契约。

## 4. 方案比较

### 方案 A：保留 Router 与 Supervisor，只修改规则

改动较小，但排他式选路和全局来源优先级仍然存在。后续新增工具时容易再次出现证据被屏蔽的问题，不采用。

### 方案 B：单 Orchestrator + 多检索器 + 确定性证据融合

Router 改为非排他的 Query Planner，Supervisor 替换为 Evidence Fusion。普通问题由多个检索器提供候选，融合层按相关性、权威性、时效性和覆盖度选择证据。结构简单、可测试、适合当前数据规模，采用此方案。

### 方案 C：Planner、Retriever、Judge、Writer 全部使用 LLM Agent

表达上更接近“多 Agent”，但成本、延迟、不可复现性和调试难度明显上升。待基础检索稳定、端到端指标可靠后再评估，不纳入本次重构。

## 5. 目标架构

```text
用户问题 + 最近对话
        ↓
Query Planner
  - 上下文补全
  - 实体/年份/部门/资料类型提取
  - 子问题拆分
        ↓
Retrieval Manager
  ├─ Campus Hybrid Retriever（官网知识库）
  ├─ Document Retriever（用户/共享文档）
  ├─ Structured Retrievers（下载、电话、专业、入口、就业）
  └─ Live Tools（天气、地图、学术搜索）
        ↓
Evidence Fusion
  - 归一化
  - 去重与 Parent 扩展
  - 排序与多样化
  - 子问题覆盖检查
        ↓
Answer Generator
  - 仅使用选定证据
  - 按 claim 引用
  - 低覆盖时明确兜底
```

这里的“多 Agent”指可并行执行、职责独立的专业工作单元，不再把每个简单查询函数包装成自治 Agent。普通问答是一条稳定流水线；只有复合问题才拆成多个子问题并行取证。

## 6. 组件设计

### 6.1 Orchestrator

保留 `AgentController` 的 API 入口职责，但内部简化为一个固定流程：

1. 调用 Query Planner 生成 `RetrievalPlan`。
2. 调用 Retrieval Manager 执行计划。
3. 调用 Evidence Fusion 生成每个子问题的最终证据。
4. 无充分证据时返回可解释的 fallback。
5. 有证据时交给 AnswerGenerator。

Orchestrator 不再包含 `fast/collab/hybrid` 模式。迁移阶段继续发送现有 `router/supervisor` SSE 事件，但内容分别映射自 Query Planner 与 Evidence Fusion，仅用于兼容当前前端状态展示；阶段 4 同步更新前端后删除这两个兼容事件。核心 `meta/token/done` 契约始终保留，并可在 `meta` 中增加可选的诊断摘要。

### 6.2 Query Planner

Query Planner 取代当前 Router，但不决定“只能调用哪个来源”。输出内容包括：

- 原始问题与结合最近对话补全后的独立问题；
- 一个或多个子问题；
- 识别出的年份、部门、校区、专业、资料类型等过滤条件；
- 建议执行的检索器列表；
- 是否属于纯实时问题。

第一版使用确定性规则和轻量文本处理。只有无规则命中或多意图难以拆分时，才允许可选的 LLM 补全；LLM 失败必须回退到默认校园 RAG，不得阻断回答。

默认策略：

- 普通校园问题：执行官网混合检索。
- 下载、电话、专业、入口、就业等问题：执行对应结构化检索；如果问题还包含政策、条件、流程或说明，同时执行官网 RAG。
- 纯天气、纯路线、纯学术搜索：只调用对应实时/外部工具。
- 复合问题：按子问题分别执行，不使用整轮全局优先级。

### 6.3 Retrieval Manager

Retrieval Manager 只负责执行计划和收集原始候选，不做最终裁决。无依赖的检索器并行运行；单个检索器失败时保留其他结果，并记录失败原因。

普通校园 RAG 不因结构化工具“非空”而被取消。结构化检索只有达到高相关性并完全覆盖纯查找问题时，才可不运行补充 RAG。

### 6.4 统一证据契约

所有 RAG、文档和工具统一返回 `Evidence`：

```text
evidence_id       稳定证据 ID
source_type       campus_rag / user_document / structured / live_api
source_name       检索器或工具名称
title
url
content           可供回答使用的正文或结构化摘要
doc_id            稳定文档 ID，可为空
parent_id         Parent 章节 ID，可为空
publish_date
department
relevance_score   0~1，检索器内部相关度
authority_score   0~1，官网/用户文档/API 等来源权威度
freshness_score   0~1，需要时计算
matched_fields    命中的标题、年份、部门等字段
subquestion_id    支持的子问题
metadata          其他展示或下载字段
```

不同检索器的原始分数不能直接比较。融合层优先使用排名融合和规则校验，避免把向量距离与字符串匹配分数直接相加。

### 6.5 Evidence Fusion

Evidence Fusion 替代当前 Supervisor，但它是确定性领域服务，不是 Agent。处理顺序固定为：

1. 丢弃低于各检索器最低相关性门槛的候选。
2. 按 `evidence_id`、规范化 URL、`doc_id + parent_id` 去重。
3. 对关键词与向量候选使用 Reciprocal Rank Fusion。
4. 每个文档在 Parent 扩展前最多保留有限数量 Child，防止一个文档占满候选。
5. 选择 Child 后再扩展对应 Parent。
6. 按子问题分别选择证据，检查每个子问题是否被覆盖。
7. 保留冲突证据并优先最新、权威来源，无法裁决时在回答中说明。

初始建议参数：每个召回器先取 30 个候选，融合后每个子问题保留 5～8 条独立证据；具体值由评测集调整，不作为硬编码业务规则。

### 6.6 结构化检索器

删除“所有二字片段任意命中”的通用策略。第一版采用字段加权的确定性评分：

- 完整标题或核心实体短语命中权重最高；
- 标题命中高于摘要、标签和分类命中；
- 年份、部门、资料类型作为过滤或强加分条件；
- 通用词如“下载、哪里、学校、申请”不得单独形成高分；
- 先评分、再去重、最后 Top-K；
- 返回 `matched_fields` 和 `relevance_score`，便于解释和测试。

下载、电话、专业、入口和就业检索器共享证据结构，但保留各自字段解析逻辑。

### 6.7 RAG 召回与切分

保留 Parent-Child 思路，但调整检索顺序：

```text
关键词召回 + 向量召回
→ 候选融合
→ 阈值过滤
→ 按 doc_id / parent_id 去重和多样化
→ 选择 Child
→ Parent 扩展
→ 最终证据截断
```

切分原则：

- 短文档保持单块。
- 长文档先按标题层级形成 Parent，再在 Parent 内切 Child。
- Child 目标约 350～600 个中文字符，重叠约 50～80；Parent 通常不超过 800～1500 字符。
- 培养方案、招生章程、通知、下载清单允许使用不同参数配置。
- 向量文本继续包含文档标题、部门、章节路径和正文。
- 检索命中 Child 后只扩展该 Parent，不默认拉取整份长文档。

建库必须使用稳定 `doc_id` 和索引版本；重建前验证 cleaned、metadata 与向量输入的对应关系。评测集引用 `doc_id`，标题只用于展示。

### 6.8 Answer Generator、置信度与 fallback

AnswerGenerator 只接收融合后证据，并保留证据分数和子问题归属。来源列表按独立文档去重，不能把同一文档的多个 Chunk 当作多个独立来源。

置信度由以下因素共同决定：

- 子问题覆盖率；
- 证据相关性；
- 是否有权威来源；
- 是否存在未解决冲突；
- 独立来源数量，而非 Chunk 数量。

以下情况触发 fallback 或部分回答：

- 所有候选低于相关性门槛；
- 某个关键子问题没有证据；
- 工具失败且 RAG 也无依据；
- 证据互相冲突且无法根据时间或权威性裁决。

## 7. 代码删改边界

计划新增：

- `backend/rag/contracts.py`：`RetrievalPlan`、`SubQuestion`、`Evidence`。
- `backend/rag/query_planner.py`：上下文补全、实体提取和检索计划。
- `backend/rag/retrieval_manager.py`：并行执行检索器。
- `backend/rag/evidence_fusion.py`：归一化、去重、融合和覆盖检查。

计划修改：

- `backend/agents/controller.py`：改成固定 Orchestrator 流程。
- `backend/agents/answer_generator.py`：接受统一证据并重新计算置信度。
- `backend/rag/retriever.py`：混合召回、过召回、去重后 Parent 扩展。
- `backend/rag/vector_store.py`：提供稳定 ID、批量取 Parent 和索引信息。
- `backend/tools/base.py` 及结构化工具：统一证据输出和字段评分。
- `crawler/build_kb.py`、`crawler/chunking.py`：稳定 doc ID、索引一致性检查和按类型切分。
- `analytics/evaluation.py`、`analytics/run_analysis.py`：使用稳定 ID 和端到端指标。
- `frontend/src/chatStore.js`、`frontend/src/embeddedChatStore.js`、聊天展示组件：阶段 4 移除旧 Router/Supervisor 状态字段，改为展示可选的检索与证据摘要。

计划退役：

- `backend/agents/supervisor.py`。
- `backend/agents/llm_router.py`。
- `backend/agents/router.py` 中的 `fast/collab/hybrid`、规则顺序优先级和重复关键词表。

退役文件应在新流水线通过回归测试后删除，不进行一次性大爆炸替换。

## 8. 迁移阶段

### 阶段 0：建立失败基线

- 为已复现问题添加端到端测试。
- 记录现有路由、工具候选、RAG 候选和最终证据。
- 建立稳定 ID 的最小黄金问题集。

### 阶段 1：统一证据与修复结构化检索

- 引入 `Evidence` 契约。
- 修复下载、电话、专业、入口等工具的评分、去重和 Top-K 顺序。
- 保持旧 Controller 可运行，通过适配器兼容旧结果。

### 阶段 2：替换 Router 与 Supervisor

- 引入 Query Planner、Retrieval Manager 和 Evidence Fusion。
- Controller 切换到新固定流水线。
- 取消来源类型全局优先级和 hard gate。
- 暂时映射旧 `router/supervisor` SSE 事件，保持 API 与前端响应兼容。

### 阶段 3：改造 RAG 与知识库

- 增加关键词 + 向量混合召回。
- 修复过召回、去重、Parent 扩展与补位顺序。
- 加入稳定 doc ID、索引版本和数据一致性校验。
- 重建并验证知识库。

### 阶段 4：评测、清理与文档

- 完成端到端评测和性能基线。
- 删除旧 Router、LLMRouter、Supervisor 和兼容字段。
- 同步更新前端聊天状态与编排展示，移除旧 `router/supervisor` 事件消费逻辑。
- 更新开发文档、架构说明和演示用例。

## 9. 测试策略

### 单元测试

- Query Planner：单意图、多意图、多轮省略实体、无规则命中。
- 结构化检索：精确短语、常见词噪声、年份/部门过滤、排序后 Top-K。
- Evidence Fusion：跨来源去重、Parent 去重、冲突、覆盖率和独立来源计数。
- Chunking：标题层级、Parent/Child 归属、短文档和表格型文本。

### 集成测试

- 工具正确项位于原始数据后部时仍进入最终证据。
- 工具为空、低相关或失败时 RAG 能正常补充。
- RAG 多个 Child 命中同一 Parent 后会补入其他文档。
- 登录用户文档不会无条件压制官网证据。
- SSE 始终以 `done` 结束。

### 端到端黄金问题

首批必须包含：

- 缓考申请表下载。
- 学生证补办规定和表格。
- 学籍异动政策与申请表。
- 白云校区网络报障电话。
- 招生章程、专业目录和调剂要求。
- 校医院就医与医保说明。
- 多轮追问“那申请条件呢”。
- 路线 + 天气 + 校园办事复合问题。

评测至少输出 Recall@K、MRR、独立文档数、证据覆盖率、引用正确率、fallback 正确率和端到端延迟。

## 10. 可观测性

每次请求生成 `trace_id`，记录但不向普通用户展示以下阶段数据：

- 规划后的独立问题和子问题；
- 每个检索器的原始候选数、过滤数、去重数；
- 最终证据及选择/淘汰原因；
- 未覆盖子问题与 fallback 原因；
- 各阶段耗时。

日志不得记录用户上传文档全文或敏感个人信息。

## 11. 验收标准

全部满足后才删除旧编排实现：

1. “缓考申请表”正确附件进入最终证据，且不再受原始文件顺序影响。
2. 错误但非空的工具结果不能阻止正确 RAG 证据进入融合层。
3. 最终证据按独立文档计数，同一文档重复 Chunk 不提升置信度。
4. Parent 合并后能补足其他高相关候选。
5. 多轮追问能保留上一轮的核心实体、年份和文档对象。
6. 现有聊天、流式输出、附件和来源展示保持兼容。
7. 新黄金问题集的官网 RAG Recall@5 不低于 90%，关键下载/电话精确查询 Top-3 命中率不低于 95%。
8. 所有新增单元、集成和端到端测试通过，旧功能无明显回归。

## 12. 实施原则

- 分阶段替换，每阶段保持应用可运行。
- 先写失败测试，再修改实现。
- 不同时改动无关前端页面或业务模块。
- 不通过扩大 Prompt、硬编码特例或无限增加 Top-K 掩盖检索问题。
- 新架构稳定前保留旧文件作为短期回退，但不维护两套长期并行逻辑。
