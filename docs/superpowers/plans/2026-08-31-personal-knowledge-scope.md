# 个人知识库检索范围实施计划

> 日期：2026-08-31  
> 状态：已实施  
> 实施节奏：下一轮从 Task 0 开始，每轮完成一个 Task 并通过对应测试后再继续。

## 1. 背景

当前个人文档已经写入独立的 `user_docs` 集合，并通过 `user_id` 做权限隔离；但普通聊天页面发送 `context_hint=null`，Planner 只有识别到“我的文档、我上传的、这份培养方案”等表达时才会选择 `user_docs`。

因此，“信计大一要学什么”即使存在已上传培养方案，也可能只选择 `campus_rag`，甚至被 LLM Planner 误选为 `academic_search`。这不是向量检索没有命中，而是个人知识库根本没有进入本次检索范围。

## 2. 已确认的产品语义

前端提供三种资料范围：

```text
自动
结合个人资料
仅个人资料
```

对应的后端稳定值：

```python
KnowledgeScope = Literal[
    "auto",
    "with_personal",
    "personal_only",
]
```

### 2.1 自动 `auto`

- 保持当前默认的校园检索能力：`campus_rag`、`shared_docs`、结构化工具和实时工具由 Planner 正常选择。
- 强制排除 `user_docs`，即使用户已经登录并上传了文档。
- LLM 输出中的 `user_docs` 也必须由服务端移除。
- 这是所有新会话和未传字段请求的默认模式，保持 API 向后兼容。

### 2.2 结合个人资料 `with_personal`

- 先生成与 `auto` 完全相同的默认检索计划。
- 在默认计划基础上叠加 `user_docs`，不得替换或删除原有校园资料、共享文档和工具。
- `user_docs` 是用户显式选择的检索覆盖层，不计入 LLM 每个子问题最多 4 个目标的配额。
- 私有文档证据不获得固定加权，不因“来自个人知识库”就自动优先。
- 默认证据和个人证据一起进入 RRF、去重和 Evidence Gate；无关个人证据不得进入最终引用。

### 2.3 仅个人资料 `personal_only`

- 每个子问题只允许检索 `user_docs`。
- 禁止补搜 `campus_rag`、`shared_docs`、结构化工具和实时工具。
- 证据不足时明确提示个人知识库未覆盖，不得静默改用校园公开资料。

## 3. 边界行为

### 3.1 登录和空知识库

| 情况 | 行为 |
|---|---|
| 未登录 + `auto` | 正常使用默认校园检索 |
| 未登录 + `with_personal` / `personal_only` | API 返回明确的 401；前端提示登录后使用 |
| 已登录但个人知识库为空 + `with_personal` | 保留默认检索，诊断标记个人库为空 |
| 已登录但个人知识库为空 + `personal_only` | 返回个人知识库为空的 fallback，不检索公开资料 |

### 3.2 简单和实时问题

用户选择 `with_personal` 时，系统仍会按定义追加个人知识库检索；但：

- 不给私有证据额外权重；
- 无关私有片段应被融合排序和 Evidence Gate 淘汰；
- 天气、路线等答案仍应以对应实时工具证据为准；
- 最终来源卡片不得展示未支持答案的个人文档。

用户若不希望发生个人文档检索，应选择默认的 `auto`。

### 3.3 多意图问题

`with_personal` 先保留 Planner 的全部默认子问题和检索目标，再为每个子问题叠加 `user_docs`。例如：

```text
“根据培养方案说明大一课程，并告诉我当前选课规定”

默认计划：
- 大一课程 -> campus_rag / shared_docs / major_search
- 当前规定 -> campus_rag

结合个人资料后的有效计划：
- 大一课程 -> campus_rag / shared_docs / major_search + user_docs
- 当前规定 -> campus_rag + user_docs
```

## 4. API 与数据契约

### 4.1 ChatRequest

修改 `backend/api/chat.py`：

```python
class ChatRequest(BaseModel):
    ...
    knowledge_scope: KnowledgeScope = "auto"
```

`context_hint` 继续表示页面上下文，不再承担个人知识库开关职责。

### 4.2 RetrievalPlan

修改 `backend/rag/contracts.py`：

```python
class RetrievalPlan(BaseModel):
    ...
    knowledge_scope: KnowledgeScope = "auto"
    base_retrievers: list[RetrievalTarget] = Field(default_factory=list)
```

- `base_retrievers` 保存 Planner 在默认模式下选择的目标。
- `retrievers` 表示应用资料范围后的最终有效目标。
- `trace_id` 全程不变。

### 4.3 Planner 接口

修改 `backend/rag/query_planner.py`：

```python
async def plan(
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
    user_id: int | None = None,
    context_hint: str | None = None,
    knowledge_scope: KnowledgeScope = "auto",
    has_personal_documents: bool = False,
) -> RetrievalPlan:
    ...
```

LLM 和规则只生成默认计划；随后由确定性函数应用用户选择：

```python
apply_knowledge_scope(
    base_plan,
    knowledge_scope,
    user_id,
    has_personal_documents,
)
```

LLM 不允许覆盖 `knowledge_scope`。

## 5. 确定性资料范围算法

```python
def apply_knowledge_scope(plan, scope, user_id, has_personal_documents):
    base = remove_user_docs(plan)

    if scope == "auto":
        return base

    require_authenticated_user(user_id)

    if scope == "with_personal":
        if not has_personal_documents:
            return base.with_diagnostic("personal_documents_empty")
        return add_user_docs_overlay(base)

    if scope == "personal_only":
        if not has_personal_documents:
            return unsupported_private_plan("personal_documents_empty")
        return replace_all_targets_with_user_docs(base)
```

安全约束：

- 所有 `user_docs` 实际调用必须同时携带 `user_id`。
- `with_personal` 不得删除默认检索目标。
- `personal_only` 的重试仍只能使用 `user_docs`。
- 自动模式下必须移除 LLM 或历史上下文引入的 `user_docs`。
- 范围诊断只记录范围与个人库使用状态，不记录私有文档正文；最终来源仍须经过 Evidence Gate 过滤。

## 6. “课程安排误选 academic_search”纠偏

本计划同时修复原问题暴露出的独立误路由：

- `academic_search` 只用于论文、文献、参考文献、研究成果和学术前沿。
- 培养方案、课程设置、学分、教学计划、大一课程不得选择 `academic_search`。
- LLM Prompt 增加正反例。
- 服务端校验发现“课程/培养方案问题 + academic_search，但不存在论文/文献意图”时移除 `academic_search`。
- 默认模式下改用 Planner 选出的校园/共享文档/专业检索目标；结合模式还会叠加 `user_docs`。

## 7. 前端交互

修改：

- `frontend/src/pages/ChatPage.jsx`
- `frontend/src/chatStore.js`
- `frontend/src/embeddedChatStore.js`
- 对应 CSS 文件

在输入框附近增加资料范围选择器：

```text
资料范围：[自动 ▾]
```

要求：

- 默认值为 `auto`。
- 当前选择必须始终可见，避免用户忘记正在使用“仅个人资料”。
- 发送请求时写入 `knowledge_scope`。
- 未登录时禁用两个个人资料模式，并提供登录提示。
- 用户退出登录时自动恢复 `auto`。
- 模式可在当前设备持久化，但不得随聊天历史消息反向恢复旧模式。
- `embeddedChatStore` 默认传 `auto`，不根据页面 key 隐式切换个人资料范围。

## 8. 诊断与响应

在 SSE `router` / `retrieval` 事件和 `retrieval_summary` 中增加：

```json
{
  "knowledge_scope": "with_personal",
  "base_retrievers": ["campus_rag", "major_search"],
  "effective_retrievers": ["campus_rag", "major_search", "user_docs"],
  "personal_documents_requested": true,
  "personal_documents_available": true,
  "personal_documents_used": true
}
```

这组字段不得包含私有文档正文。

## 9. 分步实施任务

## Task 0：先写资料范围失败测试

**Files:**

- Create: `backend/tests/test_knowledge_scope.py`
- Modify: `backend/tests/test_hybrid_query_planner.py`

**用例：**

1. 登录用户存在个人文档，`auto` 仍不得出现 `user_docs`。
2. `with_personal` 的结果必须是默认 retrievers 与 `user_docs` 的并集。
3. `personal_only` 最终 retrievers 只能是 `user_docs`。
4. LLM 输出 `user_docs` 时，`auto` 必须强制移除。
5. LLM 未输出 `user_docs` 时，`with_personal` 必须强制添加。
6. 未登录用户不能使用两个个人模式。
7. 个人知识库为空时符合第 3.1 节行为。
8. “信计大一要学什么”不得选择 `academic_search`。

**验收：** 新测试在修改前稳定失败，且不调用外部 LLM/API。

## Task 1：建立 API 和 RetrievalPlan 契约

**Files:**

- Modify: `backend/rag/contracts.py`
- Modify: `backend/api/chat.py`
- Modify: `backend/agents/controller.py`
- Modify: API schema tests

**内容：**

- 增加 `KnowledgeScope`。
- ChatRequest 默认 `auto`。
- Controller 将 scope 传入 Planner。
- Chat API 查询当前用户是否存在个人文档。
- 个人模式未登录时返回明确错误。

**验收：** 旧请求不传字段仍能工作；新字段 OpenAPI schema 正确。

## Task 2：实现 Planner 确定性资料范围

**Files:**

- Modify: `backend/rag/query_planner.py`
- Modify: `backend/rag/contracts.py`
- Modify: `backend/tests/test_knowledge_scope.py`

**内容：**

- Planner 先生成默认计划，再统一应用 scope。
- 保存 `base_retrievers` 和有效 `retrievers`。
- `with_personal` 叠加 `user_docs`。
- `personal_only` 替换为 `user_docs`。
- 自动模式无条件排除 `user_docs`。
- 修复培养方案/课程误选 `academic_search`。

**验收：** Task 0 的 Planner 测试全部通过。

## Task 3：实现 Retrieval Manager 覆盖层和重试约束

**Files:**

- Modify: `backend/rag/retrieval_manager.py`
- Modify: `backend/rag/retriever.py`
- Modify: `backend/tests/test_document_retrieval_scope.py`
- Modify: `backend/tests/test_targeted_retrieval_retry.py`

**内容：**

- `with_personal` 保留默认 tasks 并追加带 `user_id` 的 user_docs tasks。
- `personal_only` 不创建任何公开资料或工具 tasks。
- 重试不得突破 scope。
- 私有文档相关诊断不记录正文。

**验收：** 可从 mock 调用列表证明实际调用与三种模式一致。

## Task 4：前端资料范围选择器

**Files:**

- Modify: `frontend/src/pages/ChatPage.jsx`
- Modify: `frontend/src/chatStore.js`
- Modify: `frontend/src/embeddedChatStore.js`
- Modify: chat page CSS
- Create/Modify: frontend store tests

**内容：**

- 增加三项选择器并保持当前值可见。
- 请求体携带 `knowledge_scope`。
- 未登录禁用个人模式。
- 登出恢复自动模式。

**验收：** 浏览器请求载荷和 UI 状态与选择一致。

## Task 5：防止结合模式过度依赖个人资料

**Files:**

- Modify: `backend/rag/evidence_gate.py`（仅在现有逻辑不足时）
- Modify: `backend/rag/retrieval_manager.py`
- Create: `backend/tests/test_personal_evidence_balance.py`

**用例：**

1. `with_personal` 问天气：个人培养方案片段不得成为支持证据或最终引用。
2. `with_personal` 问信计课程：培养方案证据可以支持回答，公开资料仍保留。
3. 私有文档与公开资料年份冲突：Gate 返回 partial/conflict，不静默选一边。
4. 多个无关私有 Chunk 不能压制单条直接相关公开证据。
5. `personal_only` 无命中时必须 fallback，不能补用公开资料。

**验收：** 无关个人资料不会因为用户选择结合模式而影响答案结论。

## Task 6：诊断、文档和完整回归

**Files:**

- Modify: `backend/rag/retrieval_manager.py`
- Modify: `backend/agents/controller.py`
- Modify: `.env.example`（如需新增默认配置）
- Modify: `docs/ZHKU_Campus_Agent_开发.md`
- Modify: PlantUML 流程图

**内容：**

- 输出 scope、基础/有效 retrievers 和个人库使用状态。
- 更新开发文档和流程图。
- 运行后端全量测试、前端测试及构建。

**最终验收：**

- `auto` 与当前默认公共检索行为兼容且不搜索个人资料。
- `with_personal` 严格等于默认检索能力加个人知识库，不替换默认来源。
- `personal_only` 不发生公开资料或工具调用。
- 所有私有检索均带当前用户 `user_id`。
- “信计大一要学什么”在结合模式中会检索个人培养方案，且不再误走学术论文搜索。
- 简单问题不会引用无关个人文档。
- 旧 `/api/chat` 和 `/api/chat/stream` 调用不传新字段仍正常工作。

## 10. 实施结果

Task 0 至 Task 6 已按计划完成。范围选择、服务端二次校验、个人资料证据平衡、
SSE/非流式诊断、开发文档和 PlantUML 流程图均已落地；最终回归结果记录在本轮
执行说明中。
