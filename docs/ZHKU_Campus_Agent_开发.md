# ZHKU Campus Agent 开发说明（面向开发人员精简版）

> 项目名称：**ZHKU Campus Agent：仲恺校园信息服务智能体**  
> 项目方向：智慧校园 / 校园信息服务 / RAG + Agent 应用  
> 适用对象：开发人员、项目成员、测试人员、答辩展示准备人员  
> 整理版本：v1.0-dev  
> 整理日期：2026-07-21  
> 数据依据：仲恺农业工程学院官网及公开二级站点

---

## 0. 核心硬约束

本项目必须遵守以下要求，若后续需求描述与本节冲突，以本节为准。

1. **技术栈要求**
   - 后端使用 **Python + FastAPI**。
   - Agent / RAG 编排使用 **LangChain**，需要复杂流程时可引入 **LangGraph**。
   - 前端无技术要求
   - LLM 使用接入 **DeepSeek API（DS API）** 的方式。
   - 向量库可选 Chroma / FAISS / Qdrant；MVP 推荐 Chroma 或 FAISS。
   - 结构化数据可先用 SQLite，后续可切换 MYSQL。

2. **数据来源要求**
   - 项目数据必须来自仲恺农业工程学院官网及公开二级站点。
   - 主入口为：https://www.zhku.edu.cn/
   - 不使用无法确认来源的第三方资料。
   - 不采集登录后数据，不绕过验证码或权限限制。
   - 不保存学生个人隐私、课表、成绩、财务、人事等敏感数据。

3. **回答可信要求**
   - 系统回答必须尽量展示来源标题、来源部门、来源 URL、发布时间或更新时间。
   - 没有可靠依据时，必须明确提示“未在当前已采集的公开资料中找到可靠依据”。
   - 不得编造电话、地址、开放时间、报销比例、招生计划、专业设置、办事流程或内部系统入口。
   
4. **核心功能实现**

   （1）检索增强生成（RAG）：利用平台内置的知识库功能，上传领域相关专业资料，完成知识库构建与配置，确保智能体基于上传的知识精准响应查询，避免无关回答。

   （2）工具调用与交互设计：利用平台提供的内置工具或可接入的第三方 API（如天气查询、图像生成、文档转换等），完成至少一种工具的配置与调用，将工具功能融入智能体的响应流程；设计简洁、易用的交互界面（可使用平台模板编辑），支持用户便捷操作。

   （3）功能稳定性：确保智能体可稳定响应用户指令，无明显卡顿、报错，工具调用流程顺畅，RAG 检索精准，能有效解决设定场景中的实际问题。

---

## 1. 项目定位

**ZHKU Campus Agent** 是一个基于仲恺农业工程学院公开网站信息构建的校园信息服务智能体。

系统面向学生、教师、研究生、考生家长和访客，提供：

- 学校信息问答；
- 学院、机构、专业查询；
- 教务资料、培养方案、研究生资料检索；
- 招生就业信息导航；
- 后勤、网络、校医院等公共服务入口查询；
- 官网网页、PDF、Word、章程、制度、申请表的智能文档问答与摘要；
- 带来源引用的可信回答。

项目重点不是复制官网，而是实现：

```text
公开官网资料
  ↓
采集清洗与文档解析
  ↓
结构化数据库 + 向量知识库 + 智能文档索引
  ↓
Agent 意图识别与任务路由
  ↓
RAG 检索 + 文档问答 + 结构化工具查询
  ↓
可信回答 + 来源展示 + 附件/入口导航
```

---

## 2. 项目边界

### 2.1 包含范围

| 模块 | 说明 |
|---|---|
| 学校公开信息问答 | 学校概况、历史沿革、校区、联系电话、办学信息等 |
| 机构与学院查询 | 党政机构、教学机构、教辅科研机构、服务平台等 |
| 专业与培养方案 | 本科专业目录、专业所属学院、培养方案附件入口 |
| 招生与研究生信息 | 本科招生、研究生招生、招生章程、招生专业目录、相关下载 |
| 教务资料下载 | 学生下载、学籍学位、成绩、考务、培养方案等公开资料 |
| 公共服务入口 | 后勤、网络、校医院、采购招标、邮箱、VPN、OA 等公开入口 |
| 新闻公告检索 | 学校要闻、通知公告、校园快讯、二级站点通知 |
| 智能文档 | PDF / DOC / DOCX / 网页长文的问答、摘要、抽取和对比 |

### 2.2 不包含范围

| 不做内容 | 原因 |
|---|---|
| 个人课表、成绩、财务、人事数据 | 需要统一身份认证和学校授权 |
| 自动提交申请表、自动办理流程 | 涉及审批权限和业务系统集成 |
| 登录型系统深度抓取 | 只做入口导航，不抓取登录后数据 |
| 未确认的校园卡挂失、图书馆预约等固定功能 | 未在第一批公开数据中作为稳定 MVP 范围 |
| 绕过验证码或权限下载附件 | 不符合合规要求 |

---

## 3. 第一批数据来源

优先采集公开、稳定、可支撑问答和工具查询的页面。

| 信息类别 | 推荐来源 |
|---|---|
| 官网首页、快捷入口、校区地址 | https://www.zhku.edu.cn/ |
| 学校概况 | https://www.zhku.edu.cn/xxgk.htm |
| 机构设置 | https://www.zhku.edu.cn/jgsz.htm |
| 招生就业 | https://www.zhku.edu.cn/zsjy.htm |
| 本科专业目录 | https://jwc.zhku.edu.cn/info/1094/5377.htm |
| 2024 版培养方案 | https://jwc.zhku.edu.cn/xsfw/pyfa2024.htm |
| 教务资料下载 | https://jwc.zhku.edu.cn/jwfw/jwzlxz.htm |
| 学生下载 | https://jwc.zhku.edu.cn/jwfw/jwzlxz/xsxz.htm |
| 研究生处 | https://yjs.zhku.edu.cn/ |
| 就业指导中心 | https://job.zhku.edu.cn/web/index/job-list |
| 总务后勤部 | https://hqyzc.zhku.edu.cn/ |
| 后勤联系方式 | https://hqyzc.zhku.edu.cn/bmgk/lxwm.htm |
| 现代教育技术中心 | https://wlzx.zhku.edu.cn/ |
| 校医院 | https://xys.zhku.edu.cn/ |
| 新生就医指引 | https://xys.zhku.edu.cn/info/1180/1542.htm |
| 医药费报销审核 | https://xys.zhku.edu.cn/info/1160/1322.htm |

---

## 4. MVP 功能范围

MVP 不追求覆盖完整官网，先实现一个可运行、可演示、可验证的闭环。

### 4.1 第一版必须覆盖的 6 个模块

| 模块 | 目标 |
|---|---|
| 学校概况与校区信息 | 支持基础问答，展示来源 |
| 机构学院导航 | 查询学院、部门、机构类型和官网入口 |
| 本科专业与培养方案 | 查询专业、专业代码、所属学院、培养方案附件 |
| 教务资料下载 | 查询免修、缓考、学生证补办、成绩复查等表格 |
| 研究生招生与研究生下载 | 查询招生章程、招生专业目录、研究生常用表格 |
| 公共服务入口与联系方式 | 查询后勤、网络、校医院、邮箱、VPN、OA 等入口或电话 |

### 4.2 第一版必须实现的能力

1. Web 前端可以输入自然语言问题。
2. FastAPI 后端提供统一问答接口。
3. 回答基于已采集的官网公开资料。
4. 至少有一个向量知识库。
5. 至少有三个结构化工具：
   - `major_search`
   - `download_resource_search`
   - `contact_or_service_search`
6. 至少实现一个智能文档能力：
   - 文档问答；
   - 文档摘要；
   - 关键字段抽取；
   - 多文档对比。
7. 回答展示来源和附件入口。
8. 查询不到可靠依据时触发兜底。
9. 管理端或脚本支持重新采集、清洗和重建知识库。
10. 提供部署说明、演示问题集和测试结果。

---

## 5. 系统架构

```text
frontend
  ├── 首页 / 角色入口
  ├── 智能问答页
  ├── 资料下载页
  ├── 智能文档页
  └── 服务导航页

backend: FastAPI
  ├── Chat API
  ├── Search API
  ├── Resource API
  ├── Document QA API
  └── Admin API

agent layer
  ├── Agent Controller
  ├── Query Planner（声明可并行检索器）
  ├── Retrieval Manager（并行取证与一次性补检索）
  ├── Evidence Fusion（去重与多源融合）
  ├── Evidence Gate（可回答性门控）
  ├── Answer Generator
  └── Fallback Checker

说明：旧 `QuestionRouter`、`EvidenceSupervisor` 和 `LLMRouter` 仅作为兼容模块保留，
不参与默认请求链路，也不再决定某一种证据的全局优先级。

knowledge layer
  ├── RAG Retriever
  ├── Document Retriever
  ├── Vector Store
  ├── Structured DB
  └── Source Metadata

crawler layer
  ├── Page Crawler
  ├── Attachment Extractor
  ├── Document Parser
  ├── Data Cleaner
  └── KB Builder
```

---

## 6. Agent 工作流

### 6.1 基础流程

```text
用户问题
  ↓
问题规范化与概念提取
  ↓
Query Planner 声明检索计划
  ↓
Retrieval Manager 并行尝试 RAG、用户文档和结构化工具
  ↓
Evidence Fusion 去重并保留多来源证据
  ↓
Evidence Gate 评估概念覆盖；不足时最多补检索一次
  ↓
有依据 → 调用 DeepSeek 生成回答
无依据 → Fallback Checker 兜底
  ↓
引用检查、事实约束与 retrieval_summary
  ↓
返回答案、来源、附件、入口和置信度
```

### 6.2 检索计划示例

| 用户问题 | 意图 | 处理方式 |
|---|---|---|
| 学校有几个校区？ | 学校概况 | `school_profile_rag` |
| 学校有哪些学院？ | 机构查询 | `organization_search` |
| 数据科学与大数据技术专业培养方案在哪里？ | 专业 + 培养方案 | `major_search` + `training_plan_search` |
| 缓考申请表在哪里下载？ | 教务资料 | `download_resource_search` |
| 研究生免修课程申请表在哪里？ | 研究生资料 | `graduate_resource_search` |
| 白云校区网络报障电话是多少？ | 联系方式 | `contact_search` |
| 这份招生章程讲了什么？ | 智能文档 | `document_summary` 或 `document_qa` |
| 本科招生章程和研究生招生章程有什么区别？ | 多文档对比 | `document_compare` |
| 学校有没有自动办理所有请假手续的入口？ | 未公开或越界 | 兜底，不编造 |

---

## 7. RAG 与智能文档设计

### 7.1 全站 RAG

用于回答学校公开信息问题，例如学校概况、机构、公告、服务指南等。

建议集合：

| 向量集合 | 内容 |
|---|---|
| `school_profile_docs` | 学校概况、校区、历史、联系方式 |
| `organization_docs` | 学院、部门、机构设置 |
| `undergraduate_docs` | 本科专业、培养方案、教务资料 |
| `graduate_docs` | 研究生招生、培养、学位、下载 |
| `admission_docs` | 本科招生章程、选考科目、录取情况 |
| `service_docs` | 后勤、网络、校医院、公共服务 |
| `news_docs` | 新闻公告、通知、校园快讯 |
| `download_docs` | 附件标题、来源页面、文件类型和适用对象 |

### 7.2 智能文档 RAG

智能文档面向 PDF、Word、章程、制度、培养方案、申请表等资料。它解决的问题不是“文件在哪里”，而是“文件里面怎么说”。

支持能力：

| 能力 | 说明 |
|---|---|
| 文档问答 | 用户围绕某份文档连续提问 |
| 文档摘要 | 生成短摘要、详细摘要和要点列表 |
| 关键字段抽取 | 抽取材料、对象、时间、地点、电话、流程 |
| 办理清单生成 | 根据申请表或指南生成准备清单 |
| 跨文档检索 | 同时检索多个相关文档 |
| 跨文档对比 | 对比不同年份、不同专业或不同章程 |
| 来源定位 | 展示文档名、来源页面、页码或片段 |

### 7.3 文档处理流程

```text
采集官网文档入口
  ↓
下载公开附件或记录附件元数据
  ↓
解析 PDF / DOC / DOCX / HTML 长文
  ↓
提取标题、正文、章节、表格、页码
  ↓
生成文档摘要与标签
  ↓
按章节和语义切分
  ↓
写入文档级索引 + 片段级向量索引
  ↓
支持文档问答、摘要、抽取、对比
```

知识库构建采用 Parent-Child 切分：父片段保留章节上下文，子片段用于召回，
并为每份文档和片段写入稳定的 `doc_id`、`chunk_id`、`kb_schema_version` 与
`chunking_version`。重建前先校验清洗数据与元数据的一一对应关系，校验失败时不清空旧集合。
检索结果进入回答前还要经过概念覆盖门控；“有候选”不等于“足以回答”，最多执行一次扩大召回补救。

---

## 8. 数据采集与清洗

### 8.1 采集流程

```text
配置官网与二级站点入口
  ↓
爬取公开栏目链接
  ↓
提取标题、正文、发布时间、来源部门、URL
  ↓
识别附件名称、附件类型、附件入口
  ↓
过滤导航、页脚、重复内容、图片说明
  ↓
按模块分类
  ↓
保存 cleaned Markdown / JSON 与同名 metadata
  ↓
生成 `metadata_by_function.json` 功能索引并抽查关键页面
  ↓
切分文本并生成 Embedding
  ↓
写入向量库和结构化数据库
```

就业职位和招聘活动保留 `job_postings.json` / `job_fairs.json` 聚合列表，同时为每条已下载详情生成同名 metadata：

```text
data/cleaned/job/job_<id>.txt   ↔   data/metadata/job/job_<id>.json
data/cleaned/job/event_<id>.txt ↔   data/metadata/job/event_<id>.json
```

`run_all` 完成采集后会刷新功能索引；`build_kb` 清空旧向量集合前会再次刷新索引并检查上述就业正文/metadata 对齐，检查失败时不删除旧集合。

### 8.2 采集原则

优先采集：

- 与学生、教师、研究生、考生和访客直接相关的信息；
- 官网或公开二级站点发布的信息；
- 有明确标题、发布时间和来源 URL 的内容；
- 可长期复用的基础信息；
- 可支撑问答、下载、导航、流程说明的资料；
- 可抽取为结构化数据的信息，如学院、专业、联系方式、系统入口。

暂不采集：

- 登录后才能访问的数据；
- 学生个人信息、成绩、课表、财务、处分等敏感内容；
- 无法确认来源的转载内容；
- 过旧且无参考价值的通知；
- 需要验证码或权限才能下载的附件正文；
- 宣传图、装饰图、重复导航。

---

## 9. 核心数据模型

### 9.1 结构化表

```text
organization
- id
- name
- type              # 党政机构 / 教学机构 / 教辅科研机构 / 服务平台
- website_url
- parent_id
- source_url
- updated_at

major
- id
- major_code
- major_name
- college_name
- discipline_category
- degree_category
- training_plan_url
- source_url
- updated_at

download_resource
- id
- title
- category          # 教务 / 研究生 / 招生 / 医疗 / 后勤 / 网络
- audience          # 学生 / 教师 / 研究生 / 考生 / 访客
- file_type
- source_page_url
- file_url
- publish_date
- department
- keywords
- is_public
- crawl_time

service_link
- id
- name
- category          # 教务 / 科研 / 行政 / 后勤 / 网络 / 医疗 / 就业
- url
- requires_login
- user_role
- description
- source_url

contact
- id
- department
- office_name
- campus
- service_scope
- phone
- address
- source_url
- updated_at

news_article
- id
- title
- category
- department
- publish_date
- source_url
- summary
- content
- crawl_time
```

### 9.2 文档索引表

```text
document
- id
- title
- department
- category
- source_page_url
- file_url
- file_type
- publish_date
- summary
- tags
- parse_status
- created_at

document_chunk
- id
- document_id
- section_title
- page_number
- chunk_text
- embedding_id
- token_count
- chunk_index

document_qa_log
- id
- document_id
- question
- retrieved_chunks
- answer
- created_at
```

### 9.3 向量片段 metadata

```json
{
  "doc_id": "jwc_download_20260428_001",
  "title": "仲恺农业工程学院免修申请表(2026年版）",
  "department": "教务部",
  "category": "教务资料下载",
  "audience": "学生",
  "source_url": "https://jwc.zhku.edu.cn/...",
  "publish_date": "2026-04-28",
  "file_type": "doc",
  "chunk_index": 0,
  "crawl_time": "2026-07-21",
  "is_attachment": true
}
```

---

## 10. 后端 API 设计

### 10.1 问答接口

`POST /api/chat`

请求：

```json
{
  "question": "缓考申请表在哪里下载？",
  "user_role": "student",
  "session_id": "optional-session-id"
}
```

响应：

```json
{
  "answer": "回答正文",
  "confidence": "high",
  "intent": "download_resource",
  "sources": [
    {
      "title": "来源标题",
      "department": "教务部",
      "url": "https://...",
      "publish_date": "2025-04-07",
      "snippet": "命中的文本片段"
    }
  ],
  "attachments": [
    {
      "name": "仲恺农业工程学院缓考申请表（2025版）",
      "file_type": "doc",
      "source_page_url": "https://..."
    }
  ],
  "service_links": [],
  "tools_used": ["download_resource_search"],
  "fallback": false
}
```

### 10.2 资源检索接口

`GET /api/resources/downloads?keyword=缓考&category=教学与教务&audience=本科生&top_k=20`

`keyword` 执行文本匹配，`category` 和 `audience` 对真实 metadata 做精确过滤，多个条件取交集。响应中的 `category`、`audience`、`source_page_url` 来自资源条目或父级 metadata，不由请求参数伪造；`total` 是截断前总数。

响应示例：

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

前端资料分类选项直接使用响应 `facets.categories`，不再维护旧分类常量。

### 10.2.1 就业信息接口

```text
GET /api/resources/jobs?kind=posting&keyword=Python&company=广州&top_k=50
GET /api/resources/jobs?kind=fair&keyword=宣讲会&top_k=50
```

`kind` 只能是 `posting`（公开职位）或 `fair`（招聘活动），其他值返回 422。接口读取就业聚合 JSON，过滤失败条目，并返回统一字段：

```json
{
  "total": 100,
  "items": [
    {
      "id": "133257",
      "kind": "posting",
      "title": "管培生薪酬5K起",
      "company": "深圳市乐有家控股集团有限公司",
      "published": "07/18 发布",
      "salary": "5K-8K",
      "education": "本科",
      "location": "广州",
      "url": "https://job.zhku.edu.cn/web/index/job-detail?id=133257"
    }
  ]
}
```

就业聚合数据损坏或缺失时返回 503“就业数据暂不可用”，不能把服务错误伪装成空列表。

### 10.3 专业查询接口

`GET /api/majors/search?keyword=数据科学与大数据技术`

返回专业名称、专业代码、所属学院、培养方案入口和来源。

### 10.4 服务入口接口

`GET /api/services/search?keyword=VPN&role=teacher`

返回服务名称、入口 URL、是否需要登录、适用角色和来源。

### 10.5 联系方式接口

`GET /api/contacts/search?keyword=网络报障&campus=白云`

返回部门、科室、电话、校区、地址、来源。

### 10.6 文档问答接口

`POST /api/documents/{document_id}/qa`

请求：

```json
{
  "question": "这份培养方案里有哪些核心课程？"
}
```

响应：

```json
{
  "answer": "基于文档片段生成的回答",
  "document_title": "2024版本科专业人才培养方案",
  "citations": [
    {
      "page_number": 5,
      "section_title": "课程体系",
      "snippet": "命中文档片段"
    }
  ],
  "fallback": false
}
```

### 10.7 管理接口

| 接口 | 作用 |
|---|---|
| `POST /api/admin/kb/rebuild` | 提交知识库重建任务（当前为占位接口） |
| `GET /api/admin/links/check` | 提交来源 URL 检测任务（当前为占位接口） |
| `POST /api/admin/crawl/run` | 提交官网采集任务（当前为占位接口） |

---

## 11. 推荐项目目录

```text
zhku-campus-agent/
├── backend/
│   ├── app.py
│   ├── api/
│   │   ├── chat.py
│   │   ├── search.py
│   │   ├── resources.py
│   │   ├── documents.py
│   │   └── admin.py
│   ├── agents/
│   │   ├── controller.py
│   │   ├── router.py
│   │   ├── answer_generator.py
│   │   └── fallback.py
│   ├── rag/
│   │   ├── retriever.py
│   │   ├── embedder.py
│   │   ├── vector_store.py
│   │   └── prompt_templates.py
│   ├── tools/
│   │   ├── major_tool.py
│   │   ├── download_tool.py
│   │   ├── contact_tool.py
│   │   ├── service_link_tool.py
│   │   ├── document_tool.py
│   │   └── news_tool.py
│   ├── database/
│   │   ├── models.py
│   │   ├── schema.sql
│   │   └── seed.py
│   └── config.py
├── crawler/
│   ├── crawl_zhku_main.py
│   ├── crawl_jwc.py
│   ├── crawl_yjs.py
│   ├── crawl_job.py
│   ├── crawl_services.py
│   ├── parse_documents.py
│   └── build_kb.py
├── frontend/
│   ├── src/
│   └── package.json
├── data/
│   ├── raw/
│   ├── cleaned/
│   ├── metadata/
│   ├── sqlite/
│   └── vector_store/
├── docs/
│   ├── project-dev.md
│   ├── api.md
│   ├── deployment.md
│   └── test_questions.md
├── README.md
├── requirements.txt
├── docker-compose.yml
└── .env.example
```

---

## 12. 推荐技术栈

| 层级 | 推荐 |
|---|---|
| 后端 | Python + FastAPI |
| Agent 编排 | LangChain / LangGraph |
| LLM | DeepSeek API |
| Embedding | bge-small-zh / bge-m3 / text2vec / 可用中文 Embedding API |
| 向量库 | Chroma / FAISS / Qdrant |
| 结构化数据库 | SQLite / PostgreSQL |
| 关键词搜索 | SQLite FTS / Meilisearch / Elasticsearch |
| 前端 | Vue / React / Streamlit |
| 数据采集 | requests + BeautifulSoup / trafilatura / Playwright |
| 文档解析 | PyMuPDF / pdfplumber / python-docx |
| 调度 | APScheduler / cron |
| 部署 | Docker / Conda / venv |

MVP 推荐组合：

```text
FastAPI + LangChain + DeepSeek API + SQLite + Chroma + Streamlit/Vue
```

---

## 13. 前端页面设计

| 页面 | 功能 |
|---|---|
| 首页 | 项目简介、角色入口、常用模块 |
| 智能问答 | 聊天式问答，展示答案、来源、附件、工具调用 |
| 学校概况 | 学校简介、校区、历史、联系方式 |
| 学院机构 | 学院和部门列表，支持搜索 |
| 专业培养 | 本科专业目录和培养方案入口 |
| 资料下载 | 教务、研究生、招生、医保等资料分类检索 |
| 智能文档 | 文档问答、摘要、字段抽取、多文档对比 |
| 服务导航 | OA、邮箱、VPN、就业、后勤、校医院等入口 |
| 管理后台 | 数据更新、知识库重建、链接检测、日志查看 |

问答结果推荐展示：

```text
直接答案
  ↓
关键结论 / 操作步骤
  ↓
相关附件 / 服务入口
  ↓
来源引用
  ↓
更新时间 / 置信度 / 工具调用结果
```

---

## 14. Prompt 与回答规则

### 14.1 系统 Prompt 要点

Agent 应遵守：

1. 只基于已采集的仲恺农业工程学院公开资料回答。
2. 优先引用来源，不确定时不回答具体数值。
3. 涉及电话、地点、时间、报销、招生、学籍等事项时必须展示来源。
4. 如果多个来源冲突，提示用户以最新官网页面为准。
5. 如果检索不到可靠资料，触发兜底，不编造。
6. 对用户问题进行意图识别，并选择合适工具。
7. 对复杂问题可拆分为多个子任务。

### 14.2 兜底回答模板

```text
未在当前已采集的仲恺农业工程学院公开资料中找到可靠依据。
为避免提供错误信息，建议你访问对应部门官网或联系学校相关部门确认。
```

---

## 15. 开发路线

### 阶段 1：需求与数据源确认

产出：

- MVP 功能清单；
- 第一批采集页面；
- 数据表初稿；
- 演示问题集。

### 阶段 2：数据采集与清洗

产出：

- raw HTML / 附件元数据；
- cleaned Markdown / TXT；
- metadata JSON / CSV；
- 下载资源清单；
- 服务入口清单。

### 阶段 3：知识库与数据库

产出：

- SQLite 数据库；
- Chroma / FAISS 向量库；
- 文档切分与索引脚本；
- 数据字典；
- 检索测试结果。

### 阶段 4：后端与 Agent

产出：

- FastAPI 服务；
- Agent Controller；
- RAG 检索模块；
- 结构化工具；
- 文档问答工具；
- 兜底逻辑；
- API 测试文档。

### 阶段 5：前端与演示

产出：

- Web Demo；
- 问答页；
- 资料下载页；
- 服务导航页；
- 来源展示组件。

### 阶段 6：测试与交付

产出：

- 测试问题集；
- 检索准确率测试；
- 兜底测试；
- 链接有效性测试；
- README；
- 部署说明；
- 演示 PPT 和视频。

---

## 16. 测试方案

### 16.1 测试问题分类

| 分类 | 测试内容 |
|---|---|
| 学校概况 | 校区、历史、办学定位、联系方式 |
| 机构学院 | 学院列表、部门入口、服务平台 |
| 专业培养 | 专业目录、培养方案、专业代码 |
| 教务下载 | 申请表、流程图、考试规则、学籍资料 |
| 研究生服务 | 招生章程、专业目录、研究生下载表 |
| 招生信息 | 招生章程、录取情况、选考科目 |
| 就业服务 | 职位、宣讲会、招聘会、政策法规 |
| 后勤网络医疗 | 电话、地点、流程、材料、入口 |
| 越界问题 | 未公开信息、个人信息、内部系统 |

### 16.2 评价指标

| 指标 | 说明 |
|---|---|
| 检索命中率 | Top-K 结果是否包含正确来源 |
| 回答准确率 | 生成内容是否与来源一致 |
| 引用完整率 | 是否展示标题、URL、发布时间 |
| 工具调用准确率 | 是否选择正确结构化工具 |
| 兜底正确率 | 无依据问题是否拒绝编造 |
| 链接有效率 | 来源 URL 和附件入口是否可访问 |
| 响应速度 | 普通问答和工具查询耗时 |
| 用户体验 | 前端展示是否清晰、可操作 |

---

## 17. 主要风险与应对

| 风险 | 应对 |
|---|---|
| 官网结构变化 | 采集器配置化，定期链接检测 |
| 附件下载受限 | 保存来源页面和附件名，不绕过限制 |
| 信息过期 | 显示发布时间，定期重采集 |
| 数据范围过大 | MVP 只覆盖核心模块 |
| RAG 误匹配 | 使用 metadata 过滤部门、年份、类别 |
| 大模型编造 | 强制来源检查和兜底模板 |
| 登录系统不可采集 | 只做入口导航 |
| 隐私与安全 | 只采集公开网页，日志脱敏 |
| 前后端工作量大 | 先用 Streamlit 做轻量 Demo，再升级 Vue / React |

---

## 18. MVP 演示问题

| 场景 | 示例问题 | 展示能力 |
|---|---|---|
| 学校概况 | 仲恺农业工程学院有几个校区？ | RAG + 来源引用 |
| 机构导航 | 学校有哪些教学机构？ | 结构化查询 |
| 专业查询 | 数据科学与大数据技术专业培养方案在哪里？ | 专业工具 + 附件入口 |
| 教务资料 | 补办学生证申请表在哪里？ | 下载资源工具 |
| 研究生服务 | 研究生免修课程申请表在哪里？ | 研究生下载检索 |
| 后勤联系 | 后勤维修科电话是多少？ | 联系方式工具 |
| 网络服务 | 白云校区网络报障电话是多少？ | 联系方式工具 |
| 校医院 | 去校医院看病需要带什么？ | RAG + 服务信息 |
| 招生查询 | 2026 年本科招生章程在哪里？ | 招生资料检索 |
| 兜底能力 | 学校有没有自动办理所有请假手续的入口？ | 无依据兜底 |

---

## 19. 开发优先级建议

### P0：必须完成

- FastAPI 后端；
- DeepSeek API 接入；
- 基础 RAG；
- SQLite 数据库；
- 至少 3 个结构化工具；
- 来源展示；
- 兜底逻辑；
- 简单前端问答页。

### P1：建议完成

- 智能文档问答；
- 资料下载中心；
- 服务入口导航；
- 管理端重建知识库；
- 链接检测脚本；
- 测试问题集。

### P2：有时间再做

- 多文档对比；
- 新闻公告聚合；
- 就业职位结构化检索；
- 用户反馈统计；
- 更完整的 Vue / React 前端；
- Docker Compose 部署。

---

## 20. 项目结论

ZHKU Campus Agent 的合理实现方向是：

> 用 FastAPI 搭建后端，用 LangChain / LangGraph 编排 Agent，用 DeepSeek API 生成回答，用官网公开资料构建 RAG 与智能文档知识库，用 SQLite 保存学院、专业、联系方式、服务入口和资料下载等结构化数据，最终通过 Web 前端提供可追溯、可引用、不编造的校园信息服务。

项目第一版不需要做成完整校园门户，也不需要覆盖所有二级站点。重点是完成一个可靠闭环：

```text
用户自然语言提问
  ↓
Agent 判断问题类型
  ↓
选择 RAG / 文档问答 / 结构化工具
  ↓
检索官网公开资料
  ↓
生成带来源的可信回答
  ↓
前端展示答案、附件和服务入口
```
