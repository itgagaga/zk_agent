# 新增资料检索与就业数据闭环修复方案

> 状态：待评审，尚未实施。本文只定义修复思路、范围、数据契约和验收标准，不修改业务代码。

## 1. 目标

让新增资料从“采集成功”真正走通到“可精确筛选、可直接浏览、可正确进入 RAG、可重复重建”的完整链路，并解决以下六类问题：

1. 下载资料的 `category` 只是模糊搜索词，不是精确过滤条件。
2. 下载接口用请求参数或默认值伪造返回的 `category`、`audience`。
3. 前端仍使用旧分类，与新 metadata 分类口径不一致。
4. 就业职位和招聘活动只有聚合 JSON，没有结构化 API 和页面入口。
5. 完整采集后不会自动重建 `metadata_by_function.json`。
6. 就业正文与聚合 metadata 无法按文件名对应，进入向量库后标题、来源 URL 等字段可能缺失或错误。

## 2. 已核实的仓库现状

### 2.1 代码证据

- `backend/api/resources.py:233` 使用 `keyword or category` 生成查询文本，没有执行分类精确过滤。
- `backend/api/resources.py:241-242` 直接把请求中的 `category` 和 `audience` 写回响应；未传 `audience` 时固定显示“学生”。
- `backend/tools/download_tool.py:34-45` 把分类字段拼进全文匹配，但返回资源时读取父级 metadata，未优先读取资源条目自己的分类和来源页字段。
- `frontend/src/pages/DownloadsPage.jsx:60` 仍硬编码“学生下载、学籍学位、考务、培养方案、研究生培养、研究生招生”等旧分类。
- `crawler/run_all.py` 采集结束只提示手动运行 `crawler.build_kb`，没有刷新功能索引。
- `crawler/build_kb.py:43` 按清洗文件名查找同名 metadata；例如 `job_133257.txt` 会查找 `data/metadata/job/job_133257.json`。
- `crawler/crawl_job.py:163-201` 只保存 `job_postings.json` 和 `job_fairs.json` 两个聚合文件，不生成上述同名 metadata。

### 2.2 数据证据（2026-08-18 本地样本）

| 指标 | 当前值 | 结论 |
|---|---:|---|
| 职位聚合条目 | 100 | 数据已采集 |
| 职位详情下载成功 | 100 | 正文已存在 |
| 招聘活动聚合条目 | 10 | 数据已采集 |
| 招聘活动详情下载成功 | 10 | 正文已存在 |
| `data/cleaned/job/job_*.txt` | 100 | 可进入建库遍历 |
| 单条就业 metadata | 0 | 与正文无法一一对应 |
| 功能索引中的就业项 | 3 | 只反映聚合文件和服务指南，不反映 110 条详情 |

现有相关测试基线为 `20 passed`。测试只覆盖采集解析、分类和资源下载基础能力，尚未覆盖接口精确过滤、真实响应 metadata、就业 API、单条就业 metadata 对齐和采集后索引刷新。

## 3. 方案比较

### 方案 A：仅修补当前接口和前端常量

修改下载接口过滤逻辑、替换前端分类常量，并在就业聚合 JSON 上直接增加一个接口。

- 优点：改动最少，短期上线快。
- 缺点：分类仍在前后端重复维护；就业 RAG metadata 缺失和索引过期问题没有形成稳定约束，下次采集仍可能回归。

### 方案 B：统一数据契约 + 就业数据双视图（推荐）

把 metadata 作为返回字段的唯一事实来源；过滤条件与关键词检索分离；下载筛选项从后端实际 facets 生成。就业数据保留聚合 JSON 供列表 API 使用，同时为每个职位/活动生成与清洗正文同名的 metadata，供分类索引和向量建库使用。完整采集后刷新功能索引，建库入口在清空向量库前再做一次防御性刷新和一致性检查。

- 优点：一次解决六个问题；保留现有 JSON 架构，无需数据库迁移；列表浏览和 RAG 各自使用最适合的数据形态。
- 缺点：需要同时修改采集、工具、API、前端和测试，实施范围中等。

### 方案 C：把就业数据只放入向量库，继续依赖 RAG

- 优点：无需新增页面和结构化接口。
- 缺点：用户无法稳定浏览、筛选或核对职位列表；向量召回不能替代精确列表查询；不满足当前问题的核心诉求。

结论：采用方案 B。

## 4. 目标架构与数据流

```text
公开网站
  └─ crawler
      ├─ 聚合 metadata（列表 API）
      │   ├─ job_postings.json
      │   └─ job_fairs.json
      ├─ 单条 metadata（分类索引 + RAG）
      │   ├─ job_<id>.json
      │   └─ event_<id>.json
      └─ 清洗正文
          ├─ job_<id>.txt
          └─ event_<id>.txt
                 │
                 ├─ build_functional_index → metadata_by_function.json
                 └─ build_kb → Chroma metadata

metadata JSON → backend/tools → /api/resources/* → DownloadsPage
```

### 4.1 分类和筛选契约

- `keyword`：只执行标题、摘要、部门、标签等文本匹配。
- `category`：对候选资源的真实 `category` 做精确相等过滤。
- `audience`：对候选资源的真实 `audience` 做精确相等过滤。
- 响应字段优先级：资源条目字段 > 父级 metadata 字段 > 空字符串；禁止使用请求参数或固定默认值伪造 metadata。
- `source_page_url` 优先读取资源条目的 `source_page_url`，其次读取父级 `source_url`。
- `total` 表示过滤、去重后的总数，不是被 `top_k` 截断后的数组长度。
- 下载接口同时返回基于真实候选资源聚合的 `facets.categories` 和 `facets.audiences`，前端不再维护旧分类常量。

建议接口响应：

```json
{
  "total": 12,
  "items": [
    {
      "title": "学生证申请表.docx",
      "category": "教学与教务",
      "audience": "本科生",
      "source_page_url": "https://jwc.zhku.edu.cn/...",
      "file_url": "https://jwc.zhku.edu.cn/.../form.docx"
    }
  ],
  "facets": {
    "categories": ["教学与教务", "研究生教育与招生"],
    "audiences": ["本科生", "研究生"]
  }
}
```

### 4.2 就业双视图契约

聚合文件继续保存列表所需字段，并作为结构化 API 的数据源：

- `GET /api/resources/jobs?kind=posting&keyword=&company=&top_k=50`
- `GET /api/resources/jobs?kind=fair&keyword=&company=&top_k=50`
- `kind` 只允许 `posting` 或 `fair`，非法值返回 422。
- API 只返回 `status=downloaded` 或具有可访问官方 URL 的有效条目；`url` 指向职位/活动官方详情页。
- `total` 为过滤后的真实总数。

单条 metadata 与正文严格同名：

```text
data/cleaned/job/job_133257.txt
data/metadata/job/job_133257.json

data/cleaned/job/event_5301.txt
data/metadata/job/event_5301.json
```

单条 metadata 至少包含：

```json
{
  "id": "133257",
  "title": "管培生薪酬5K起",
  "company": "深圳市乐有家控股集团有限公司",
  "source_url": "https://job.zhku.edu.cn/web/index/job-detail?id=133257",
  "publish_date": "...",
  "category": "就业与招聘",
  "subcategory": "公开职位",
  "audience": "毕业生/求职者",
  "document_type": "职位详情"
}
```

招聘活动使用 `subcategory=校园招聘活动`、`document_type=招聘活动`。单条 metadata 的 `source_url` 必须是详情页 URL，不是列表页 URL。

### 4.3 索引和建库契约

- `crawler.run_all` 在所有采集阶段完成后执行 `build_functional_index`，即使某个非关键采集阶段失败，也对已经成功落盘的数据生成新索引，并打印分类数量摘要。
- `crawler.build_kb` 在删除旧向量集合之前再次刷新功能索引，避免用户跳过 `run_all` 或手工修改 metadata 后建出过期库。
- 建库前检查每个 `data/cleaned/job/job_*.txt`、`event_*.txt` 是否存在同名 metadata；存在缺失时终止重建并报告缺失文件，避免先清空旧集合后才发现新数据不完整。
- 向量 chunk 的 `title`、`source_url`、`category`、`subcategory`、`audience` 均来自单条 metadata。

### 4.4 前端入口

在现有 `DownloadsPage` 的“资料下载 / 服务入口”页签旁增加“就业信息”页签，不另建重复导航页面：

- 子页签：公开职位、招聘活动。
- 关键词搜索匹配职位/活动名称和公司。
- 卡片展示：标题、公司、发布时间或活动时间、地点、薪资/学历（有值才显示）。
- 唯一主操作为“查看官方详情”，打开 API 返回的详情页 URL。
- 下载资料筛选 chips 使用接口返回的 `facets.categories`，显示值和请求值完全一致。
- API 异常、空结果和加载态分别显示，不能把异常伪装成“没有数据”。

## 5. 文件影响范围

| 文件 | 责任 |
|---|---|
| `backend/tools/download_tool.py` | 分离关键词匹配与精确过滤，返回资源真实 metadata 和 facets |
| `backend/tools/job_tool.py`（新增） | 读取聚合就业 JSON，规范化、过滤、去重并返回职位/活动 |
| `backend/api/resources.py` | 修正 downloads 契约，新增 jobs API 和响应模型 |
| `frontend/src/pages/DownloadsPage.jsx` | 动态下载分类和就业信息页签 |
| `crawler/crawl_job.py` | 在保留聚合 JSON 的同时生成每条详情对应的 metadata |
| `crawler/classification.py` | 明确 `job_`/`event_` 的子分类和文档类型；保持功能索引生成稳定 |
| `crawler/run_all.py` | 增加最终功能索引阶段和摘要 |
| `crawler/build_kb.py` | 建库前刷新索引并校验就业正文/metadata 一致性 |
| `backend/tests/test_resource_download.py` | 下载精确过滤、真实 metadata、facets、total 回归测试 |
| `backend/tests/test_job_crawler.py` | 单条就业 metadata 生成和文件名对齐测试 |
| `backend/tests/test_metadata_classification.py` | `job_`/`event_` 分类和索引计数测试 |
| `backend/tests/test_job_tool.py`（新增） | 就业聚合读取、过滤、非法/失败条目处理测试 |
| `backend/tests/test_resources_api.py`（新增） | downloads/jobs API 契约测试 |
| `docs/ZHKU_Campus_Agent_开发.md` | 更新接口、采集和重建流程文档 |

## 6. 分阶段实施顺序

### 阶段 1：锁定数据契约和失败测试

先添加四组失败测试：下载精确过滤、响应真实 metadata、就业单条 metadata 对齐、就业 API 列表。此阶段不改生产逻辑，用失败结果证明测试确实覆盖当前缺陷。

### 阶段 2：修复资料查询闭环

让 `DownloadTool.run()` 显式接收 `category`、`audience`，先构造规范化候选项，再依次执行关键词匹配、精确过滤、去重和截断。API 只透传过滤参数并返回工具提供的真实字段、`total` 和 facets。

### 阶段 3：修复就业 metadata 与 RAG 对齐

采集每条职位/活动详情成功后，生成与清洗正文同名的 metadata。分类器区分 `job_` 和 `event_`。加入一致性校验后，再验证 100 个职位正文和 10 个活动正文均能找到对应 metadata。

### 阶段 4：增加就业结构化查询和页面入口

新增 `JobTool` 和 `/api/resources/jobs`，随后在 `DownloadsPage` 增加就业页签。结构化列表用于浏览和筛选，RAG 继续用于自然语言问答，两者共享同一来源 URL 和分类字段。

### 阶段 5：自动刷新索引并安全重建

在 `run_all` 末尾刷新功能索引；在 `build_kb` 清空旧集合前执行索引刷新和就业文件一致性校验。校验失败时保持旧向量库不动。

### 阶段 6：全链路验证和文档更新

运行后端测试、前端生产构建、一次 `--skip-job` 的快速采集流程测试，以及基于现有落盘就业数据的索引/建库验证。最后更新开发文档中的 API 表和数据维护命令。

## 7. 验收标准

### 7.1 下载资料

- 请求 `category=教学与教务` 时，所有返回项的真实 `category` 都严格等于“教学与教务”。
- 同时传入 `keyword` 和 `category` 时执行交集过滤，而不是二选一。
- 未传 `category`/`audience` 时，响应仍显示 metadata 中的真实值，不出现固定“学生”。
- `total` 等于过滤后总数，允许大于 `items.length`。
- 页面分类选项全部来自接口 facets，不再出现旧分类口径。

### 7.2 就业数据

- 当前样本至少可通过 API 浏览 100 条公开职位和 10 条招聘活动。
- 每个成功下载的 `job_*.txt` 和 `event_*.txt` 都存在同名 JSON metadata。
- 每条单项 metadata 的标题非空，`source_url` 为官方详情页，分类为“就业与招聘”。
- 就业卡片可以直接打开官方详情页，API 失败与零结果有不同提示。

### 7.3 索引与 RAG

- 完整采集结束后 `data/indexes/metadata_by_function.json` 自动更新。
- 功能索引能反映单条就业记录，而不只包含 2 个聚合 JSON。
- 建库前发现正文/metadata 不一致时不删除旧集合。
- 新向量 chunk 的就业标题和来源 URL 可与对应聚合条目逐项核对。

### 7.4 回归

- 当前 20 个相关测试继续通过。
- 新增测试覆盖本方案中的六个问题。
- `npm run build` 在 `frontend/` 下成功。
- 不引入新的数据库表或外部依赖。

## 8. 非目标

- 不将职位数据迁移到 MySQL；当前规模下聚合 JSON 足够支撑只读列表。
- 不实现职位收藏、投递、登录态或定时任务。
- 不用 RAG 代替结构化列表筛选。
- 不重新设计整个资料智库页面，只增加必要的筛选数据源和就业页签。
- 不处理需要登录、验证码或绕过访问控制的数据。

## 9. 风险与回滚

- 若单条 metadata 生成失败，保留聚合 JSON 和旧向量库；一致性校验阻止破坏性重建。
- 若动态 facets 暂时为空，前端仍提供“全部”，但不回退到旧硬编码分类。
- 若就业 API 读取到损坏 JSON，返回明确服务错误并记录文件路径，不返回部分伪造数据。
- 各阶段可独立提交；阶段 2、3、4、5 可以分别回滚，不修改原始 HTML 和清洗正文。

## 10. 评审后下一步

评审确认后，再基于本文生成逐任务、逐测试、逐提交的详细实施计划；实施时优先完成阶段 1-3，再决定是否立即上线就业页签。
