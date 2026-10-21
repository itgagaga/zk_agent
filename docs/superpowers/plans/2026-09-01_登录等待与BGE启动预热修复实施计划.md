# 登录等待与 BGE 启动预热修复实施计划

> 日期：2026-09-01  
> 状态：已实施（待重启验收）  
> 适用范围：FastAPI 启动生命周期、本地 BGE Embedding、Uvicorn 开发热重载  
> 核心目标：保留 `BAAI/bge-small-zh-v1.5` 预热，并在启动阶段完成准备后再提供正常服务；登录不会在服务尚未 ready 时被误认为已经可用。

## 1. 问题结论

日志中的登录请求实际成功：

```text
POST /api/auth/login HTTP/1.1 200 OK
```

前端长时间停留在登录加载状态，是因为应用启动阶段同步等待了 BGE 预热：

```text
embedding_warmup status=success ... duration_ms=26827.0
```

当前 FastAPI `lifespan` 在执行到 `yield` 之前等待 `asyncio.to_thread()` 返回。虽然模型加载发生在线程中，但应用仍处于 `Waiting for application startup`，所有接口都要等约 27 秒后才能接收请求。这个“启动完成后再正常使用”的语义是本次保留的产品要求；本次修复优化的是重载范围、状态可观测性和重复加载风险，不改成登录先可用、模型后台慢慢加载。

同时，`APP_DEBUG=true` 会让 Uvicorn WatchFiles 监控项目目录。修改 `analytics/chat_latency_smoke.py` 也会触发后端重载，导致：

1. 旧 worker 被终止；
2. Windows multiprocessing 创建新 worker；
3. 新 worker 再次加载 BGE；
4. 前端在重启窗口内暂时无法调用登录接口。

`KeyboardInterrupt` 出现在热重载/进程切换阶段，不是认证逻辑抛出的异常；HF Hub 未认证警告也不是登录失败原因。

## 2. 修复目标与非目标

### 2.1 修复目标

1. 后端在启动阶段完成 BGE 准备后再提供正常服务，登录等接口不与未完成的模型加载竞争。
2. BGE 仍在服务启动时自动预热，不删除模型、不改向量维度。
3. 启动预热与后续聊天复用同一模型实例，模型最多加载一次。
4. 预热失败不得导致进程崩溃，并提供可诊断状态。
5. 开发热重载只监控后端运行代码，修改分析脚本不再重启服务。
6. 关闭服务或热重载时，不遗留后台预热任务。

### 2.2 非目标

- 不移除 `BAAI/bge-small-zh-v1.5`。
- 不切换在线 Embedding API。
- 不重建 Chroma 向量库。
- 不修改登录鉴权、JWT、数据库或前端登录协议。
- 不把 HF Token 作为修复登录问题的前置条件。

## 3. 目标时序

```text
Uvicorn worker 启动
  ├─ 初始化基础配置和数据库表
  ├─ lifespan 标记 embedding loading
  ├─ 阻塞等待 BGE 预热结束（在线程执行，事件循环不被阻塞）
  ├─ 标记 ready 或 failed
  ├─ lifespan yield，Application startup complete
  │    └─ 登录 / 会话 / stats / 聊天正常响应
  └─ 后续请求复用已加载的 BGE，不重复初始化
```

## 4. 分阶段实施

### Task 1：将 BGE 预热固化为阻塞式启动阶段

涉及文件：

- `backend/app.py`
- `backend/config.py`
- `.env.example`

实施内容：

1. 保留 `EMBEDDING_WARMUP_ENABLED=true`。
2. 增加 `EMBEDDING_WARMUP_MODE=blocking`，支持 `blocking` 和 `disabled`；默认使用 `blocking`，不提供登录先可用的后台模式。
3. 从 lifespan 中抽出 `_warmup_embedding()` 异步函数，在 `yield` 前等待它完成。
4. 将状态保存在 `app.state.embedding_status`，启动期间依次记录 `loading`、`ready` 或 `failed`。
5. 预热在工作线程执行，避免阻塞事件循环；但 FastAPI 不在预热结束前宣布 `Application startup complete`。
6. 预热失败时结束本次启动准备并标记 `failed`，不把异常详情返回给客户端；后续 RAG 调用仍按原逻辑处理。

验收条件：

- 慢速假模型加载 30 秒时，FastAPI lifespan 在模型加载结束前不进入 `yield`。
- `Application startup complete` 出现时，BGE 已成功加载或已明确记录失败。
- 模型成功加载后状态变为 `ready`，登录请求只在服务真正启动后接收。

### Task 2：确保 Embedder 并发只初始化一次

涉及文件：

- `backend/rag/embedder.py`
- `backend/tests/test_embedding_warmup.py`（新增）

实施内容：

1. 为 `Embedder._load_local()` 增加 `threading.Lock`。
2. 使用双重检查：
   - 进入锁前检查 `_model`；
   - 获得锁后再次检查 `_model`；
   - 只有一个线程执行 `SentenceTransformer(...)`。
3. 启动预热和聊天检索复用同一个全局 Embedder 单例。
4. 不允许后续聊天在另一个线程再次下载或加载同一模型。
5. 记录加载次数只用于测试，不写入生产响应。

验收条件：

- 10 个线程同时调用 `embed_one()` 时，模型构造函数只执行一次。
- 预热未完成时发起聊天，不发生双重加载或 `_model` 半初始化。
- 原有向量归一化和 512 维输出保持不变。

### Task 3：提供安全的预热状态与健康信息

涉及文件：

- `backend/app.py`
- 对应 API 测试

实施内容：

1. `/health` 保持 HTTP 200，增加非敏感字段（服务启动完成后可访问）：

```json
{
  "status": "ok",
  "embedding_status": "ready"
}
```

2. 状态只允许：`disabled`、`loading`、`ready`、`failed`。
3. 不返回模型缓存路径、异常详情、用户信息或环境变量。
4. 若预热失败：
   - 登录、会话和非 RAG 接口继续可用；
   - 首次 RAG 调用可按原逻辑再尝试加载；
   - 日志记录 `error_type`，不记录敏感异常正文。

验收条件：

- `Application startup complete` 之后 `/health` 返回 `ready` 或 `failed`。
- 预热成功后 `/health` 返回 `ready`。
- 模型加载失败时 `/health` 可诊断，但服务不退出。

### Task 4：限制开发环境热重载范围

涉及文件：

- `backend/app.py`
- `backend/config.py`
- `.env.example`
- 启动文档

实施内容：

1. Uvicorn `reload_dirs` 只包含：
   - `backend/`
   - 必要时包含项目根目录的 `main.py` 和 `.env`，通过明确配置处理。
2. 明确排除：
   - `analytics/`
   - `docs/`
   - `frontend/`
   - `data/`
   - `.tmp/`
   - 模型和向量缓存目录。
3. 增加配置：
   - `APP_RELOAD_ENABLED=true`
   - `APP_RELOAD_DIRS=backend`
4. `APP_DEBUG` 只控制调试日志，不再隐式决定是否启动热重载；兼容期可保留旧字段映射并输出一次迁移提示。
5. 生产环境默认关闭 reload。

验收条件：

- 修改 `analytics/chat_latency_smoke.py` 不触发服务重启。
- 修改 `backend/agents/answer_generator.py` 会触发一次重启。
- 单次重启只创建一个新 worker，BGE 阻塞式预热完成后才接受登录。

### Task 5：前端启动窗口容错

此任务仅用于服务重启窗口的提示，不改变“启动完成后再提供正常服务”的语义。

涉及文件：

- 前端认证状态管理文件
- 对应前端测试

候选内容：

1. 登录请求遇到连接中断时显示“服务正在重启，请稍后重试”，不显示账号密码错误。
2. 对网络连接失败允许一次短退避重试；HTTP 401/403 不自动重试。
3. 页面刷新恢复会话时，区分：
   - 未登录；
   - 服务未就绪；
   - Token 失效。

验收条件：

- 后端热重载窗口不会误导用户修改密码。
- 真正的认证失败仍立即显示正确错误，不被网络重试掩盖。

## 5. 测试计划

### 后端单元测试

1. `blocking` 模式会等待预热完成后才进入 lifespan 的 `yield`。
2. `disabled` 模式不执行预热。
3. 预热成功、失败状态正确。
4. 多线程并发初始化只构造一次模型。
5. `/health` 不泄露异常和缓存路径。

### 集成测试

1. 使用模拟 30 秒加载的 Embedder 启动应用。
2. 验证模型完成前不会出现 `Application startup complete`。
3. 验证启动完成后登录、会话和聊天可以正常请求。
4. 模型 ready 后发起聊天，验证检索和回答正常。

### 回归测试

```powershell
pytest backend/tests/test_embedding_warmup.py -q
pytest backend/tests/test_chat_stream.py backend/tests/test_answer_generator_stream.py -q
pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run build
```

## 6. 性能验收标准

以下指标在同一开发机器、同一 Python 环境下测量：

- `Application startup complete`：在 BGE 预热完成（或明确失败）后出现。
- BGE 预热仍可耗时约 27 秒，但该时间只发生在服务启动阶段。
- `Application startup complete` 后登录接口 P95 小于 2 秒。
- 每个 worker 的 BGE 构造次数不超过 1。
- 修改 `analytics/` 文件后 30 秒内服务进程 PID 不变化。
- 修改 `backend/` 文件时只触发一次预期重载。

## 7. 风险与回滚

| 风险 | 缓解措施 | 回滚方式 |
|---|---|---|
| 预热失败导致服务降级 | 任务内部捕获并更新状态、记录 error_type；启动仍完成并明确标记 `failed` | 临时切换为 `disabled` |
| 热重载目录过窄导致代码不刷新 | 将必要目录显式加入 `APP_RELOAD_DIRS` | 恢复 Uvicorn 默认监控范围 |
| 多 worker 各自加载一份模型 | 明确每 worker 一份模型的内存预算 | 减少 worker 数或使用独立 Embedding 服务 |
| 健康状态被前端误当成认证状态 | 保持 `/health` 200，embedding 状态单独字段 | 移除新增字段，不影响核心服务 |

本计划不涉及数据删除和数据库迁移。回滚配置不会改变现有向量库，也不需要重新上传个人文档。

## 8. 实施结果

- Task 1：已完成。默认采用 `blocking` 启动预热；`Application startup complete` 之前不会接收正常请求。
- Task 2：已完成。Embedder 与全局实例均有并发保护，模型构造只执行一次。
- Task 3：已完成。`/health` 增加 `embedding_status`，不返回敏感错误详情。
- Task 4：已完成。热重载默认关闭，开发环境通过 `.env` 显式启用且只监控 `backend`。
- Task 5：已完成最小必要部分。登录页将服务未启动/重启与账号密码错误分开提示。

已验证：后端 `167 passed`；前端测试 `10 passed`；前端生产构建成功。

## 9. 完成定义

只有同时满足以下条件，才可标记修复完成：

- BGE 预热在 FastAPI 启动阶段完成；
- 启动完成后的请求只复用已加载模型，不重复初始化；
- 登录只在 `Application startup complete` 后提供，并不再与未完成的模型加载竞争；
- `/health` 能安全反映预热状态；
- `analytics/` 修改不再触发后端热重载；
- 后端全量测试、前端测试和构建通过；
- 实测日志不再出现“每次分析脚本变化都重启并等待 27 秒”的链路。该项需要按新的启动命令重启服务后进行人工观察。
