# 增强模式空回答与响应延迟修复实施计划

> 日期：2026-08-31  
> 状态：Task 0 基线工具、Task 1–4 已实施；Task 0 实测数据、Task 5 并发优化和最终性能验收待继续  
> 适用范围：`/api/chat/stream`、Query Planner、校园/个人资料检索、最终答案生成  
> 核心决策：保留本地 `BAAI/bge-small-zh-v1.5`，不更换 Embedding、不删除模型缓存、不重建向量库。

## 1. 背景与现象

增强模式请求“我是信计大四学生，你有什么建议”时，服务端完成了以下流程：

1. SSE 接口返回 `200 OK`，表示流已建立，不表示回答已经完成；
2. Planner 选择 `campus_rag`、`major_search`、`job_search`，增强模式再叠加 `user_docs`；
3. 首次语义检索加载本地 BGE Embedding；
4. 最终答案生成等待约一分钟；
5. 前端最终显示“模型未返回有效回答，请重试”。

目前没有证据表明 HF Hub 警告导致请求失败。`Loading weights: 100%` 表明 BGE 权重已成功从本机缓存加载。

## 2. 已确认的技术原因

### 2.1 主要原因：DeepSeek V4 默认思考与流式消费不匹配

- 当前答案模型为 `deepseek-v4-flash`。
- DeepSeek V4 默认启用思考模式，默认 effort 为 `high`。
- 思考内容通过 `reasoning_content` 返回，最终可见答案通过 `content` 返回。
- `AnswerGenerator` 设置 `max_tokens=2000`，但只把 `content` 当作可见 token。
- 如果 2000 token 主要消耗在思考阶段，模型可能在产生最终正文前以 `finish_reason=length` 结束。
- 当前代码无法记录 reasoning token、`finish_reason` 或首个正文 token 时间；当整个流没有 `content` 时，只发送通用空回答文案。

这同时解释了“长时间无文字”和“最终空回答”。

### 2.2 次要原因：增强模式链路更长

- `hybrid` Planner 在检索前先调用一次 LLM。
- 增强模式在公共检索器之外增加 `user_docs`。
- Evidence Gate 判定需要补检索时最多重试一次。
- 部分标记为 `async` 的本地检索内部仍执行同步 Embedding、Chroma 和文件读取，会阻塞事件循环。
- 每个请求都会新建 `AgentController`、Planner 和 LLM 客户端，未复用 HTTP 连接。

这些因素会增加延迟，但不是空回答的直接原因。

### 2.3 BGE 的定位

`BAAI/bge-small-zh-v1.5` 将问题和文档转换为 512 维向量，用于中文语义召回。它与 BM25 词法召回互补：

- BGE 负责同义表达、近义问题和语义相关内容；
- BM25 负责专业名、表格名、部门名等精确关键词；
- 两路结果融合后再进入证据门控和答案生成。

BGE 下载完成后在本地推理，不调用远程 Embedding API。此次修复不得删除 `sentence-transformers`、`EMBEDDING_MODEL`、现有向量或 Hugging Face 缓存。

## 3. 修复目标与非目标

### 3.1 修复目标

1. 有效模型请求不得因“只有 reasoning、没有 content”而静默变成通用空回答。
2. 普通校园问答默认使用 DeepSeek 非思考模式，缩短首个正文 token 时间。
3. Planner 和最终答案模型使用有效、明确的 V4 模型名。
4. 首次 BGE 加载从用户请求路径移到应用启动阶段。
5. 日志能够分别定位 Planner、Embedding、检索、重试、首 token 和完整生成耗时。
6. 保持标准、增强、私有三种资料范围语义和个人文档权限边界不变。

### 3.2 非目标

- 不移除或替换 BGE。
- 不切换到在线 Embedding 服务。
- 不重建 Chroma 向量库。
- 不改变现有证据融合、个人资料隔离和引用展示语义。
- 第一阶段不为了提速而减少 Planner 选择的有效检索器。
- 不在界面展示模型的原始思维链。

## 4. 分阶段实施方案

### Task 0：建立可重复的基线

### 修改内容

- 新增 `analytics/chat_latency_smoke.py`，通过 SSE 记录：
  - 请求开始到 `router`；
  - 请求开始到 `retrieval`；
  - 请求开始到首个非空 `token`；
  - 请求总耗时；
  - 是否出现空回答兜底；
  - 返回的资料范围和检索器，不保存正文或个人资料片段。
- Bearer Token 只允许从环境变量读取，禁止写入脚本和日志。
- 分别执行冷启动 1 次、预热后标准模式 10 次、增强模式 10 次。
- 保存修复前结果到 `analytics/results/chat_latency_before.json`。

### 验收

- 能明确区分 Planner、检索和生成阶段耗时。
- 记录当前空回答复现率与首 token 延迟，作为后续对比基线。

### Task 1：统一 DeepSeek Chat 配置并默认关闭思考

### 涉及文件

- `backend/config.py`
- `backend/utils/deepseek.py`（新增）
- `backend/agents/answer_generator.py`
- `backend/rag/query_planner.py`
- `backend/rag/evidence_gate.py`
- `.env.example`

### 修改内容

1. 增加配置：
   - `DEEPSEEK_THINKING_MODE=disabled`
   - `DEEPSEEK_REASONING_EFFORT=low`
   - `DEEPSEEK_TIMEOUT_SECONDS=60`
   - `DEEPSEEK_MAX_RETRIES=1`
2. 将 `DEEPSEEK_MODEL` 和 `QUERY_PLANNER_MODEL` 的默认值统一为 `deepseek-v4-flash`。
3. 新增统一客户端工厂，集中设置：
   - `extra_body={"thinking": {"type": "disabled"}}`；
   - timeout、重试次数和模型名；
   - 非思考模式下保留现有 temperature；
   - 只有显式启用思考时才传 `reasoning_effort`，且不得把 `reasoning_content` 展示给用户。
4. 第一批迁移聊天主链路的三个调用点：Planner、Evidence Gate、AnswerGenerator。
5. 地图、简历、面试、课表等非聊天入口在本任务回归后单独迁移，避免一次改动扩大故障面。

### 设计约束

- Planner 和答案生成必须显式指定思考开关，不能依赖服务端默认值。
- `max_tokens=2000` 在非思考模式下暂时保留；只有基线证明正文被截断时才调整。
- 不使用已淘汰的 `deepseek-chat` / `deepseek-reasoner` 作为默认模型名。

### 验收

- 单元测试能断言请求参数包含 `thinking.type=disabled`。
- Planner 仍能返回合法结构化计划。
- 同一问题不再先等待长时间 reasoning 才出现正文。

### Task 2：完善流式终止与空输出诊断

### 涉及文件

- `backend/agents/answer_generator.py`
- `backend/agents/controller.py`
- `backend/api/chat.py`
- `backend/utils/llm_content.py`
- `backend/tests/test_answer_generator_stream.py`
- `backend/tests/test_chat_stream.py`

### 修改内容

1. 流式生成内部记录但不输出：
   - 是否收到 reasoning 块；
   - reasoning 字符数/块数；
   - 首个正文 token 耗时；
   - 最终 `finish_reason`；
   - 模型 usage（若 SDK 提供）。
2. 将日志分为：
   - `answer_stream_started`；
   - `answer_first_token`；
   - `answer_stream_completed`；
   - `answer_stream_empty`。
3. 空输出时按原因给出稳定的内部诊断：
   - `length`：输出额度耗尽；
   - timeout / API 异常：模型服务不可用；
   - 正常结束但无正文：兼容性异常。
4. 面向用户仍使用简洁文案，不暴露思维链、SDK 对象、API Key 或完整提示词。
5. 不自动执行第二次完整 LLM 重试，避免空回答后再额外等待一分钟；网络层只保留一次短重试。
6. SSE 无论成功或失败都必须发送 `done`，前端不得永久保持 loading。

### 新增测试

- 只有 `reasoning_content`、最终 `finish_reason=length`。
- reasoning 后正常产生 `content`。
- 正常结束但 content 为空。
- API 抛出 timeout。
- SSE 中途异常仍收到错误 token 和 `done`。

### 验收

- 每个空输出都能从日志判定具体原因。
- 前端不再出现“只有资料标签、没有正文且一直 loading”的状态。

### Task 3：应用启动时预热 BGE

### 涉及文件

- `backend/app.py`
- `backend/config.py`
- `backend/rag/embedder.py`
- `.env.example`
- 新增对应生命周期测试

### 修改内容

1. 增加 `EMBEDDING_WARMUP_ENABLED=true`。
2. 在 FastAPI lifespan 中使用 `asyncio.to_thread()` 执行一次短文本 Embedding：
   - 避免阻塞事件循环；
   - 使模型权重加载发生在服务启动阶段，而不是首个聊天请求中。
3. 启动日志记录模型名、设备、加载耗时和成功/失败，不记录缓存绝对路径。
4. 保留当前全局 Embedder 单例，确保每个 worker 只初始化一次。
5. 调整离线策略：
   - 已部署环境在进程启动前显式设置 `HF_HUB_OFFLINE=1`；
   - 新环境安装时先预下载模型；
   - 不在 `_load_local()` 内临时覆盖运维传入的 HF 配置。
6. 预热失败时将 RAG 状态标记为 degraded，并输出清晰日志；是否阻止服务启动由配置控制，默认开发环境不阻止启动。

### 验收

- 服务启动日志中只出现一次 BGE 权重加载。
- 第一次聊天请求不再出现 `Loading weights`。
- 增强模式仍能查询 `user_docs`，检索结果维度与现有 Chroma 集合兼容。
- 无向量库重建和数据迁移。

### Task 4：让阶段耗时日志真正可见

### 涉及文件

- `backend/app.py` 或新增 `backend/logging_config.py`
- `backend/agents/controller.py`
- `backend/rag/retrieval_manager.py`
- `.env.example`

### 修改内容

1. 为 `backend.*` logger 配置明确的 INFO handler，避免只有 Uvicorn access log 可见。
2. 所有聊天阶段日志统一携带同一 `trace_id`。
3. 记录以下阶段：
   - Planner；
   - 初始检索；
   - Evidence Gate；
   - 定向重试；
   - 检索映射；
   - 首个正文 token；
   - 答案生成完成；
   - 请求总耗时。
4. 禁止记录用户问题正文、私有文档片段、Authorization、Cookie 和 API Key。

### 验收

- 仅凭一组相同 `trace_id` 的日志即可还原一次请求的阶段耗时。
- access log 的 `200 OK` 不再被误认为模型已经完成回答。

### Task 5：根据测量结果优化阻塞检索

此任务必须在 Task 0–4 完成并获得真实耗时后再执行，避免提前重构错误环节。

### 候选修改

1. 将同步 Chroma、Embedding、BM25 和本地文件检索移入受限线程池。
2. 对同一请求、同一规范化查询只计算一次 query embedding，在校园库和个人库之间复用。
3. 为本地 Embedder 增加并发保护，避免多个请求同时首次加载模型。
4. 复用 Agent/LLM HTTP 客户端，减少每次请求重建连接。
5. 只有日志证明 Evidence Gate 重试贡献显著延迟时，才调整 `RAG_MAX_RETRY` 或重试条件。

### 约束

- 不得通过跳过 `user_docs` 来伪造增强模式提速。
- 不得以降低个人资料隔离、过滤条件或证据门控为代价。
- 并发改造前必须增加多用户隔离与 Embedder 并发测试。

### Task 6：回归测试与性能验收

### 自动测试

```powershell
uv run pytest backend/tests/test_answer_generator_stream.py backend/tests/test_chat_stream.py -q
uv run pytest backend/tests/test_hybrid_query_planner.py backend/tests/test_knowledge_scope.py -q
uv run pytest backend/tests/test_personal_evidence_balance.py backend/tests/test_personal_scope_fallback.py -q
uv run pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run build
```

### 手工场景

| 场景 | 模式 | 预期 |
|---|---|---|
| 我是信计大四学生，你有什么建议 | 增强 | 有正文；可同时引用公共资料和当前用户资料 |
| 本科专业目录有哪些 | 标准 | 不调用 `user_docs` |
| 根据我上传的培养方案总结毕业要求 | 私有 | 只使用当前用户资料 |
| 个人资料为空时询问课程建议 | 增强 | 公共回答可用，明确个人资料未使用 |
| 模型超时 | 任意 | 显示稳定错误文案并结束 loading |
| 模型 reasoning-only | 任意 | 记录明确原因，不暴露思维链 |

### 性能目标

以下为开发环境目标，需要与 Task 0 基线一起报告，不能作为外部 API 的绝对 SLA：

- 预热后 20 次有效请求，空回答兜底出现次数为 0；
- 首个正文 token 的 P50 小于 8 秒、P95 小于 20 秒；
- 完整回答总耗时 P50 小于 15 秒、P95 小于 30 秒；
- 冷启动额外耗时只发生在应用启动阶段；
- 增强模式相对标准模式的额外检索耗时可从日志独立识别。

修复后结果保存为 `analytics/results/chat_latency_after.json`，并在同一机器、同一网络和同一问题集下生成 before/after 对比。

## 5. 实施顺序与提交边界

建议按以下顺序独立实施和验证：

1. Task 0：基线脚本与修复前数据；
2. Task 1：DeepSeek 配置与非思考模式；
3. Task 2：流式诊断与异常终止；
4. Task 3：BGE 启动预热；
5. Task 4：日志配置；
6. Task 6：功能回归和第一轮性能验收；
7. 仅在数据证明有必要时实施 Task 5；
8. 再次执行 Task 6，记录最终结果。

每个 Task 应保持可独立测试和回滚，避免把模型配置、检索重构和前端改动混入同一次提交。

## 6. 风险与回滚

| 风险 | 缓解措施 | 回滚方式 |
|---|---|---|
| 非思考模式降低复杂问题推理质量 | 校园事实问答默认关闭；后续可按场景显式开启 low | 设置 `DEEPSEEK_THINKING_MODE=enabled` |
| BGE 预热增加启动时间或内存 | 可配置开关；记录启动耗时和设备 | 设置 `EMBEDDING_WARMUP_ENABLED=false` |
| 外部 API 抖动导致性能目标不稳定 | 同网络多次采样，报告 P50/P95 | 不回滚功能修复，只标注外部依赖 |
| 线程化检索引入竞态 | Task 5 延后；先加并发与隔离测试 | 回滚 Task 5，不影响 Task 1–4 |
| 日志泄露隐私 | 只记录 trace、计数、状态和耗时 | 关闭新增 handler 并审计日志字段 |

由于保留原 BGE 和现有向量维度，本计划不涉及数据库迁移；Task 1–4 回滚也不需要重建知识库。

## 7. 完成定义

只有同时满足以下条件才可标记修复完成：

- 聊天主链路显式控制 DeepSeek 思考模式；
- Planner 与答案模型使用有效 V4 模型名；
- reasoning-only、length、timeout 和正常流均有自动测试；
- 首次聊天请求不再承担 BGE 权重加载；
- 阶段耗时日志可见且不包含敏感正文；
- 标准、增强、私有三种模式通过权限和证据回归；
- before/after 性能报告完成，空回答复现率为 0；
- 文档、`.env.example` 与实际代码配置一致。
