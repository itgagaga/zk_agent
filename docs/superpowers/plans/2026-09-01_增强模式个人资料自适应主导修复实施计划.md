# 增强模式个人资料自适应主导修复实施计划

> 日期：2026-09-01  
> 状态：实施中（Task 1–5 已完成，Task 6–7 待真实冒烟验收）  
> 实施节奏：每轮完成 2–3 个 Task，并在进入下一轮前运行对应测试。  
> 核心目标：增强模式下，按子问题判断个人资料相关性；相关时由个人资料主导回答，公共资料负责补充和校验，不相关时不强行引用个人资料。

## 1. 背景与问题结论

现有个人知识库范围、权限隔离、检索失败诊断已经完成。当前问题不再是“个人资料有没有进入检索”，而是“进入检索后是否成为最终回答的有效主依据”。

真实增强模式日志已经证明：

```text
user_docs status=success candidate_count=39
personal_hit=true personal_used=true
final evidence_count=12
```

但回答只泛化为“打好数学基础、加强软件开发能力、拓宽知识面”，没有充分利用培养方案中的课程、学分和学期安排。原因包括：

1. `user_docs` 与官网、专业工具等所有候选统一竞争固定的最终证据窗口。
2. 当前 `EvidenceFusion` 在来源角色确定前执行全局截断，相关个人章节可能被公共候选挤出。
3. “建议类”问题没有稳定拆成课程、学分、实践和阶段规划等可检索子问题。
4. Prompt 虽然声明个人文档优先，但没有要求将个人事实转化为具体、可执行的建议。
5. Evidence Gate 对开放式建议过于保守，容易把“允许基于事实推导建议”误处理为“不得给出任何证据外推导”。
6. 资料智库助手固定发送 `knowledge_scope=auto`，没有显式使用个人资料的入口。

本计划解决的是证据利用质量，不重复修改已有的 Chroma 过滤器、用户权限隔离和范围定义。

## 2. 与既有计划的关系

继续保持以下既有约束：

- `auto`：排除 `user_docs`。
- `with_personal`：允许公共资料与当前用户个人资料共同检索。
- `personal_only`：只允许当前用户的 `user_docs`。
- 所有个人资料查询必须携带当前 `user_id`。
- 个人资料失败、空库、无命中和已采用状态继续明确展示。
- 日志和前端诊断不得输出私有文档正文。

本计划只修订增强模式的证据优先级：

> 原规则“不因来自个人知识库而固定加权”调整为“不得无条件加权；只有与当前子问题相关时，才获得可解释的自适应优先级”。

## 3. 产品语义

### 3.1 按子问题判断，而不是整轮统一判断

一个问题可能同时包含多个领域：

```text
根据我的培养方案规划大一学习，并分析当前就业方向。
```

应分别处理：

- 大一课程规划：个人培养方案高相关，个人资料主导。
- 就业方向：招聘和官网数据高相关，公共/工具资料主导。

禁止用整轮的单一结果让个人资料覆盖所有子问题，也禁止因为其中一个子问题无关就删除整轮个人资料。

### 3.2 个人资料相关度

每个子问题产生稳定等级：

| 等级 | 含义 | 证据策略 |
|---|---|---|
| `high` | 问题明确指向个人文档，且个人片段直接覆盖核心要求 | 个人资料作为主要事实骨架，公共资料只补缺口和校验时效 |
| `medium` | 个人资料能解释用户背景或部分要求，但不足以单独回答 | 个人与公共资料共同使用，按覆盖增量选择 |
| `low` | 只有弱相关背景信息 | 不预留位置，只在确有新增价值时作为补充 |
| `none` | 无相关命中或存在明显冲突 | 不进入最终回答上下文和来源引用 |

`with_personal` 表示“个人资料有资格参与”，不表示“每次回答都必须引用个人资料”。

### 3.3 时效性与权威性

个人资料可以主导个人培养、课程规划和用户上传文档解释，但不能无条件覆盖最新官方事实。

- 培养方案、个人课表、个人材料：相关个人文档优先。
- 当前通知、电话、办事时间、最新政策、新闻：最新官网或实时工具优先。
- 个人资料与最新官方资料冲突：回答中明确指出差异和时间范围，不静默混合。

## 4. 性能约束

相关性判断必须复用现有检索结果，不增加新的 LLM、Embedding 或外部 API 调用。

性能目标：

- 自适应策略自身 P95 小于 100ms。
- 相比旧链路，预热后的检索阶段 P95 增量小于 150ms。
- 首 token P95 增量小于 300ms。
- 不为凑数量再次扩大检索或补充无关片段。
- 不启用当前默认关闭的本地 reranker 和 LLM Evidence Judge；如后续需要，单独评估。

## 5. 动态证据选择算法

### 5.1 禁止随机抽取和固定条数硬切

不采用“个人最多 5 条、官网最多 4 条、工具最多 3 条”的最终策略。固定条数仅可作为故障保护，不作为质量决策。

最终上下文使用动态信息预算：

1. 先按来源和子问题保留通过最低相关性门槛的候选。
2. 合并同一 Parent/章节的相邻片段，课程表和完整章节优先保持结构。
3. 每轮选择能带来最大新增覆盖的信息。
4. 高度重复、冲突或不能增加新信息的片段跳过。
5. 达到上下文字符预算或边际收益阈值后停止。
6. 未使用的预算可在个人、官网和工具来源之间动态调剂。

### 5.2 证据效用分数

不调用 LLM，使用现有信号计算：

```text
utility = 基础相关性
        + 子问题覆盖增益
        + 新信息/章节多样性
        + 来源角色奖励
        + 权威性与时效奖励
        - 内容重复惩罚
        - 专业/年份/培养层次冲突惩罚
```

信号来源：

- Dense 和 BM25 排名；
- RRF 融合分数；
- QueryPlanner 子问题；
- Evidence Gate 的概念覆盖和冲突结果；
- `doc_id / parent_id / chunk_index / title` 等结构化元数据；
- 问题中的“我的、培养方案、课表、学分、课程、这个文档”等明确指向；
- 是否属于最新通知、政策、电话、时间等时效性事实。

### 5.3 高相关个人资料如何主导

主导不等于简单增加片段数量，而是：

- 个人证据先构成该子问题的事实骨架；
- Prompt 中标为“主要依据”并排在对应子问题前；
- 课程表、学分、培养目标等完整章节优先于泛化摘要；
- 回答中的事实先引用个人文档，再由官网或工具补充；
- 公共资料不能把高相关个人事实挤出上下文；
- 如果个人证据不能覆盖某项，才使用公共资料补齐并标明来源角色。

## 6. 分阶段实施任务

### Task 0：建立质量基线与失败用例

涉及文件：

- `analytics/chat_latency_smoke.py`
- 新增 `backend/tests/test_enhanced_personal_relevance.py`
- 新增或扩展语义黄金用例

实施内容：

1. 固定真实问题：`我是信计大一的新生，你有什么建议`。
2. 使用包含培养目标、课程表、学分要求和实践环节的模拟个人文档。
3. 记录旧链路最终各来源候选数、选中数、上下文字符数和选择耗时。
4. 验证旧链路可能只保留培养目标而遗漏课程表。
5. 测试和分析结果不得保存真实用户文档正文。

验收条件：

- 失败用例能稳定区分“个人资料命中”与“个人资料真正主导回答证据”。
- 基线脚本不调用额外 Judge，不记录问题正文、Token 或回答正文。

### Task 1：增加个人资料相关性契约

涉及文件：

- `backend/rag/contracts.py`
- `backend/rag/retrieval_manager.py`
- `backend/tests/test_scope_diagnostics.py`

新增内部结构：

```python
PersonalRelevanceLevel = Literal["high", "medium", "low", "none"]

class PersonalRelevanceAssessment(BaseModel):
    subquestion_id: str
    level: PersonalRelevanceLevel
    personal_candidate_count: int
    personal_selected_count: int = 0
    matched_concepts: list[str] = []
    has_conflict: bool = False
    reason_code: str
```

要求：

- `reason_code` 使用稳定枚举，不输出文档正文。
- 对外摘要只暴露等级、数量和状态，不暴露私有片段。
- `personal_documents_used` 仍由最终选中证据推导，不能只看候选。

### Task 2：实现确定性的子问题相关性评估器

建议新增：

- `backend/rag/personal_evidence_policy.py`
- `backend/tests/test_enhanced_personal_relevance.py`

实施内容：

1. 输入子问题、个人候选和 Evidence Gate 结果。
2. 结合明确个人指向、概念覆盖、RRF 排名和冲突计算相关性等级。
3. 高相关必须满足“个人意图或直接覆盖核心要求”之一，并且没有关键冲突。
4. 仅有文档标题弱匹配不得判为高相关。
5. 新闻、天气、路线、实时电话等问题默认不能因个人库弱命中而升为高相关。
6. 不调用 LLM、Embedding 或网络。

验收用例：

- “根据我的信计培养方案安排大一学习” → `high`。
- “信计专业适合学什么语言”且个人文档覆盖课程 → `medium/high`，由覆盖度决定。
- “今天白云校区天气如何” → `none`。
- “培养方案课程 + 当前就业信息” → 不同子问题得到不同等级。
- 其他专业或年份明显冲突 → `none` 或 `low`。

### Task 3：将融合排名与最终上下文选择分离

涉及文件：

- `backend/rag/evidence_fusion.py`
- `backend/rag/retrieval_manager.py`
- `backend/config.py`
- `backend/tests/test_personal_evidence_balance.py`
- `backend/tests/test_retrieval_manager.py`

实施内容：

1. `EvidenceFusion` 负责去重和统一排序，不在个人策略执行前直接截成最终 12 条。
2. 保留一个只用于资源安全的候选池上限；它不是最终来源配额。
3. 新增动态选择器，按子问题覆盖增量和上下文字符预算选择最终证据。
4. `high`：先满足个人资料对核心概念的覆盖，再用公共证据补齐。
5. `medium`：个人与公共候选按效用共同竞争，但给予可解释的相关性奖励。
6. `low`：不预留预算，仅在能够增加新信息时保留。
7. `none`：删除个人候选，确保不会出现在 Prompt 和引用中。
8. 相邻课程表片段优先 Parent 合并；禁止五个近似片段占据五份预算。
9. 未使用预算自动交给其他有效来源。

建议配置：

```text
RAG_PERSONAL_PRIORITY_POLICY=adaptive
RAG_ANSWER_CONTEXT_MAX_CHARS=16000
RAG_CANDIDATE_SAFETY_MAX=80
RAG_EVIDENCE_MIN_UTILITY=0.0
```

具体阈值由 Task 0 基线校准，不直接照搬示例值。

### Task 4：调整建议类问题与回答 Prompt

涉及文件：

- `backend/rag/query_planner.py`
- `backend/rag/prompt_templates.py`
- `backend/agents/controller.py`
- 对应 Planner、Prompt 和生成器测试

实施内容：

1. 将“某专业某年级有什么建议”稳定拆成课程基础、技能实践、培养要求和阶段规划等子问题。
2. 向 Prompt 传递每个子问题的主要依据与辅助依据，不再只传统一 `composite` 标签。
3. 高相关个人资料存在时，回答必须使用其中的具体事实；禁止只复述培养目标。
4. 允许基于已引用事实进行明确标注的建议和推导：
   - 事实必须有证据；
   - 建议可以是基于事实的推导；
   - 不得把建议伪装成培养方案原文要求。
5. 结构优先采用“文档事实 → 针对性建议 → 可执行安排 → 来源”。
6. Evidence Gate 的边界提示区分“缺少事实”与“允许做建议性推导”，避免生成器因过度保守而敷衍。

验收条件：

- 回答能够引用培养方案中的具体课程、学分、学期或实践要求。
- 每条建议能说明与哪项个人事实相关。
- 证据没有课程表时仍如实说明，不编造课程和学分。

### Task 5：修正资料智库助手的资料范围入口

涉及文件：

- `frontend/src/components/EmbeddedChat.jsx`
- `frontend/src/embeddedChatStore.js`
- `frontend/src/pages/DownloadsPage.jsx`
- `frontend/src/knowledgeScope.js`
- 对应前端测试

实施内容：

1. 不再将嵌入式助手永久硬编码为 `auto`。
2. 登录用户可显式选择标准、增强、私有；未登录时只允许标准。
3. 默认仍为标准，禁止在用户不知情时读取个人资料。
4. 选中增强后发送 `with_personal`，复用本计划的自适应主导策略。
5. 显示“个人资料主导 / 个人资料参与 / 个人资料无关未使用”等结果状态。
6. 页面 `context_hint=资料智库` 只用于检索领域提示，不作为个人资料授权。

### Task 6：增加可观测性

涉及文件：

- `backend/rag/retrieval_manager.py`
- `backend/agents/answer_generator.py`
- `frontend/src/retrievalSummary.js`
- `frontend/src/pages/ChatPage.jsx`

新增安全日志：

```text
personal_relevance trace_id=... subquestion_id=q1 level=high
candidate_personal=... selected_personal=...
selected_public=... selected_tool=... context_chars=...
selection_duration_ms=...
```

要求：

- 不记录查询原文、文档标题、正文、用户 ID 和片段。
- 前端只展示用户可理解的资料角色，不显示内部效用分数和阈值。
- `personal_documents_used=true` 必须与最终 Prompt 中确有个人证据一致。

### Task 7：完整质量、权限与性能回归

后端测试：

```powershell
pytest backend/tests/test_enhanced_personal_relevance.py -q
pytest backend/tests/test_personal_evidence_balance.py -q
pytest backend/tests/test_personal_scope_fallback.py -q
pytest backend/tests/test_scope_diagnostics.py -q
pytest backend/tests/test_retrieval_manager.py -q
pytest backend/tests -q
```

前端测试：

```powershell
npm --prefix frontend test
npm --prefix frontend run build
```

性能验证：

```powershell
python analytics/chat_latency_smoke.py --scope with_personal --runs 10
```

验收矩阵：

| 问题 | 模式 | 预期行为 |
|---|---|---|
| 我是信计大一新生，有什么建议 | 增强 | 个人培养方案主导，包含具体事实与可执行建议 |
| 根据我的培养方案列出大一课程和学分 | 增强 | 个人相关度 high，官网仅补充或校验 |
| 今天学校有什么新闻 | 增强 | 个人相关度 none，个人资料不进入最终上下文 |
| 根据培养方案规划学习并分析就业 | 增强 | 课程子问题个人主导，就业子问题公共/工具主导 |
| 个人培养方案与最新官网规定不一致 | 增强 | 明确冲突和年份，最新时效事实以官方资料为准 |
| 只根据我的资料回答 | 私有 | 只使用当前用户个人资料，维持原权限边界 |

## 7. 分轮实施建议

### 第一轮：Task 0–2

- 建立失败基线。
- 增加相关性契约。
- 实现无额外模型调用的子问题评估器。

### 第二轮：Task 3–4

- 分离候选融合和最终选择。
- 实现动态上下文预算。
- 调整建议类问题拆分和回答 Prompt。

### 第三轮：Task 5–6

- 给资料智库助手增加显式资料范围。
- 增加日志和前端状态。

### 第四轮：Task 7

- 全量回归、真实性能测试和人工答案质量验收。

## 8. 风险与缓解

| 风险 | 缓解方式 |
|---|---|
| 个人资料被无条件提升 | 只在子问题相关度 high/medium 时加权，none 必须排除 |
| 个人旧资料覆盖最新政策 | 对时间敏感事实增加官方权威与时效优先规则 |
| 上下文增加导致回答变慢 | 使用动态字符预算、章节去重和边际收益停止条件 |
| 策略过严仍然只保留泛化摘要 | 对课程表、学分、学期等结构章节增加覆盖增益 |
| 策略过松引入无关个人信息 | 保留 Evidence Gate 冲突与最低相关性门槛 |
| 嵌入式助手静默读取个人资料 | 默认标准，只有用户显式选择后才启用增强/私有 |
| 回归影响标准或私有模式 | 自适应策略只在 `with_personal` 生效；其他模式保持原语义 |

## 9. 回滚方案

新增特性开关：

```text
RAG_PERSONAL_PRIORITY_POLICY=legacy|adaptive
```

若出现质量或性能回归：

1. 切回 `legacy`，恢复当前统一 RRF + Evidence Gate 行为。
2. 保留新增诊断字段，但前端对未知字段继续兼容。
3. 不删除个人文档、不重建向量库、不改变 `user_id` 权限过滤。
4. 资料智库助手可临时隐藏增强/私有选择，不影响标准模式。

## 10. 完成定义

只有同时满足以下条件，才可标记完成：

- 增强模式按子问题产生可解释的个人资料相关度。
- 高相关个人资料不会在最终选择前被公共候选挤出。
- 最终证据按信息覆盖和上下文预算动态选择，不依赖随机抽取或固定来源条数。
- 建议类回答能把个人文档事实转化为具体、可执行的建议。
- 无关问题不会为了体现增强模式而强行引用个人资料。
- 资料智库助手只有在用户显式选择后才使用个人资料。
- 不增加额外 LLM、Embedding 或外部 API 判断调用。
- 自适应策略 P95 小于 100ms，首 token P95 增量小于 300ms。
- 后端全量测试、前端测试和生产构建通过。
- 标准、增强、私有三种模式的权限与失败降级行为保持正确。

## 11. 当前实施记录

已完成：

- 增加自适应策略配置、候选安全池和上下文字符预算。
- 新增 `PersonalEvidencePolicy`，按子问题计算 `high / medium / low / none`，不调用额外 LLM。
- 将增强/私有模式的候选池与最终上下文选择分离；标准 `auto` 模式保持原有排序行为。
- 增强/私有模式按相关性、子问题覆盖和信息新颖度动态选择证据。
- 建议类问题的规则降级路径拆分为课程学分、实践要求和阶段规划子问题。
- Prompt 增加个人事实优先、事实与建议分离和具体化要求。
- 资料智库助手增加标准/增强/私有资料范围选择，默认仍为标准。
- 新增相关性与选择测试；后端全量测试 `172 passed`，前端测试 `10 passed`，前端生产构建成功。

待完成：

- 使用当前真实培养方案运行增强模式冒烟，核对最终回答是否出现具体课程/学分/学期事实。
- 补充选择阶段结构化日志和前端“个人资料主导/参与/无关”展示。
- 用同一机器运行 10 次延迟对比，确认选择阶段和首 token 性能指标。
