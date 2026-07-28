# ZHKU Campus Agent 开发说明（面向开发人员）

> 项目名称：**ZHKU Campus Agent：仲恺校园信息服务智能体**  
> 项目方向：智慧校园 / 校园信息服务 / RAG + Agent 应用  
> 适用对象：开发人员、项目成员、测试人员、答辩展示准备人员  
> 整理版本：**v2.0-dev**（对齐当前代码实现）  
> 整理日期：**2026-07-28**  
> 数据依据：仲恺农业工程学院官网及公开二级站点

---

## 实现进度概览

| 模块 | 状态 | 说明 |
|---|---|---|
| FastAPI 后端 | ✅ 已实现 | `backend/app.py`，含健康检查与统计接口 |
| DeepSeek API 接入 | ✅ 已实现 | 问答、简历增强、模拟面试、出行建议 |
| Agent 路由 + 多 Agent 协作 | ✅ 已实现 | `QuestionRouter`（fast / collab）+ `EvidenceSupervisor` |
| 官网 RAG | ✅ 已实现 | Chroma 集合 `zhku_campus` |
| 智能文档 RAG | ✅ 已实现 | 共享 `zhku_documents` + 用户私有 `zhku_user_docs` |
| 结构化工具（7 个） | ✅ 已实现 | 专业 / 下载 / 联系 / 入口 / 天气 / 学术 / 路线 |
| 来源展示 + 兜底 | ✅ 已实现 | `AnswerGenerator` + `FallbackHandler` |
| MySQL 结构化库 | ✅ 已实现 | 含用户、会话、简历、课表、文档元数据 |
| 数据采集脚本 | ✅ 已实现 | `crawler/run_all.py` 及分模块爬虫 |
| React + Vite 前端 | ✅ 已实现 | 问答、下载、今日校园、账户中心、简历 |
| 用户注册登录（JWT） | ✅ 已实现 | 会话持久化、个人知识库、课表、简历 |
| 流式问答（SSE） | ✅ 已实现 | `POST /api/chat/stream` |
| 模拟面试 | ✅ 已实现 | 基于简历的 LLM 对话式面试 |
| Docker Compose | ✅ 已配置 | 前后端容器编排 |
| 管理端采集/重建 | ⏳ 占位 | Admin API 已挂载，任务触发为 stub |
| 新闻公告独立检索 | ⏳ 占位 | `GET /api/search/news` 暂未实现 |

---

## 0. 核心硬约束

本项目必须遵守以下要求，若后续需求描述与本节冲突，以本节为准。

1. **技术栈要求**
   - 后端使用 **Python + FastAPI**。
   - Agent / RAG 编排使用 **LangChain**，复杂流程采用 **多 Agent 协作 + Supervisor 证据裁决**（可扩展 LangGraph）。
   - 前端：**React + Vite**（已实现完整 Web 界面）。
   - LLM 使用接入 **DeepSeek API（DS API）** 的方式。
   - 向量库：**Chroma**（MVP 已采用；可选 FAISS / Qdrant）。
   - 结构化数据库：**MySQL 8**（业务读写）；旧 SQLite 仅作一次性迁移源。

2. **数据来源要求**
   - 项目数据必须来自仲恺农业工程学院官网及公开二级站点。
   - 主入口：https://www.zhku.edu.cn/
   - 不使用无法确认来源的第三方资料。
   - 不采集登录后数据，不绕过验证码或权限限制。
   - **不保存其他学生的个人隐私、课表、成绩、财务、人事等敏感数据**；个人课表仅由用户本人上传并仅存于该用户账户下。

3. **回答可信要求**
   - 系统回答必须尽量展示来源标题、来源部门、来源 URL、发布时间或更新时间。
   - 没有可靠依据时，必须明确提示「未在当前已采集的公开资料中找到可靠依据」。
   - 不得编造电话、地址、开放时间、报销比例、招生计划、专业设置、办事流程或内部系统入口。

4. **核心功能实现（大赛赛道二要求对照）**

   （1）**检索增强生成（RAG）**：基于官网采集资料与用户上传文档构建向量知识库，Agent 检索后生成精准回答。

   （2）**工具调用与交互设计**：已实现天气查询（和风天气）、路线规划（高德地图）、学术搜索、结构化校园查询等工具，并融入 Agent 响应流程；前端提供聊天、资料下载、今日校园、账户中心等页面。

   （3）**功能稳定性**：支持流式输出、会话持久化、证据优先级裁决与兜底，避免无依据编造。

---

## 1. 项目定位

**ZHKU Campus Agent** 是一个基于仲恺农业工程学院公开网站信息构建的校园信息服务智能体。

系统面向学生、教师、研究生、考生家长和访客，提供：

- 学校信息问答（RAG + 来源引用）；
- 学院、机构、专业查询（结构化工具）；
- 教务资料、培养方案、研究生资料检索；
- 招生就业信息导航；
- 后勤、网络、校医院等公共服务入口查询；
- 官网网页、PDF、Word、章程、制度、申请表的智能文档问答；
- **用户私有知识库**（上传培养方案等文档后可在问答中检索）；
- **今日校园**（个人课表 + 天气 + LLM 出行建议 + 校区导航）；
- **简历增强与模拟面试**（就业辅助，基于用户自行填写/上传的简历）；
- 带来源引用的可信回答。

项目重点不是复制官网，而是实现：

```text
公开官网资料 + 用户授权上传文档
  ↓
采集清洗与文档解析
  ↓
MySQL 结构化库 + Chroma 向量库（官网 / 共享文档 / 用户私有）
  ↓
Agent 意图识别 → fast 单路径 / collab 多 Agent 协作
  ↓
Supervisor 证据优先级裁决
  ↓
RAG 检索 + 结构化工具 + 第三方 API（天气 / 地图 / 学术）
  ↓
DeepSeek 生成回答 + 来源展示 + 兜底
```

---

## 2. 项目边界

### 2.1 包含范围

| 模块 | 说明 |
|---|---|
| 学校公开信息问答 | 学校概况、历史沿革、校区、联系电话、办学信息等 |
| 机构与学院查询 | 党政机构、教学机构、教辅科研机构、服务平台等 |
| 专业与培养方案 | 本科专业目录、专业所属学院、培养方案附件入口 |
| 招生与研究生信息 | 本科招生、研究生招生、招生章程、招生专业目录 |
| 教务资料下载 | 学生下载、学籍学位、成绩、考务、培养方案等公开资料 |
| 公共服务入口 | 后勤、网络、校医院、采购招标、邮箱、VPN、OA 等 |
| 新闻公告检索 | 学校要闻、通知公告（向量库含新闻数据；独立 API 待完善） |
| 智能文档 | PDF / DOC / DOCX / 网页长文的问答、摘要、字段抽取 |
| 用户个人功能 | 注册登录、会话历史、个人知识库、课表上传、简历与模拟面试 |
| 第三方工具 | 天气、校区间路线规划、学术文献搜索 |

### 2.2 不包含范围

| 不做内容 | 原因 |
|---|---|
| 批量采集或共享他人课表、成绩、财务、人事数据 | 需要统一身份认证和学校授权 |
| 自动提交申请表、自动办理流程 | 涉及审批权限和业务系统集成 |
| 登录型系统深度抓取 | 只做入口导航，不抓取登录后数据 |
| 绕过验证码或权限下载附件 | 不符合合规要求 |

> **说明**：用户可在「我的课表」中**自行上传** Excel 课表，数据仅绑定该登录用户，不上传则今日校园仅展示天气与导航等公开信息。

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

**采集入口脚本**（`python -m crawler.run_all`）按顺序执行：

1. `crawl_zhku_main` — 学校主站  
2. `crawl_jwc` — 教务部  
3. `crawl_training_plans` — 培养方案 PDF  
4. `crawl_yjs` — 研究生处  
5. `crawl_job` — 就业指导中心（可用 `--skip-job` 跳过）  
6. `crawl_services` — 后勤 / 网络 / 校医院  
7. `crawl_extra` — 学生处 / 招生网 / 研究生补充 / 财务部  

采集完成后执行 `python -m crawler.build_kb` 构建向量库并写入 MySQL。

---

## 4. MVP 功能范围

### 4.1 第一版必须覆盖的 6 个模块（均已实现）

| 模块 | 目标 | 实现方式 |
|---|---|---|
| 学校概况与校区信息 | 支持基础问答，展示来源 | RAG + `/api/search/rag` |
| 机构学院导航 | 查询学院、部门、机构类型和官网入口 | `major_search` + `/api/resources/organizations` |
| 本科专业与培养方案 | 查询专业、专业代码、所属学院、培养方案附件 | `major_search` + 文档 RAG |
| 教务资料下载 | 查询免修、缓考、学生证补办、成绩复查等表格 | `download_search` + 下载页 |
| 研究生招生与研究生下载 | 查询招生章程、招生专业目录、研究生常用表格 | 爬虫 + RAG + 下载工具 |
| 公共服务入口与联系方式 | 查询后勤、网络、校医院、邮箱、VPN、OA 等 | `contact_search` + `service_link_search` |

### 4.2 第一版能力清单（对照实现）

| # | 能力 | 状态 |
|---|---|---|
| 1 | Web 前端自然语言问答 | ✅ `ChatPage` + SSE 流式 |
| 2 | FastAPI 统一问答接口 | ✅ `POST /api/chat` |
| 3 | 回答基于官网公开资料 | ✅ |
| 4 | 向量知识库 | ✅ Chroma 三集合 |
| 5 | 至少 3 个结构化工具 | ✅ 共 7 个 |
| 6 | 智能文档能力 | ✅ 问答 / 摘要 / 用户上传检索 |
| 7 | 来源与附件展示 | ✅ |
| 8 | 无依据兜底 | ✅ |
| 9 | 重新采集与重建知识库 | ⏳ 脚本已有，Admin API 为 stub |
| 10 | 部署说明与演示问题集 | ✅ README + 本文档 |

---

## 5. 系统架构（当前实现）

```text
frontend（React + Vite）
  ├── /                     首页（角色入口、模块导航）
  ├── /chat                 智能问答（流式、来源、工具结果）
  ├── /downloads            资料下载与服务入口
  ├── /campus-today         今日校园（课表、天气、出行建议、导航）
  ├── /resume               简历增强 + 模拟面试
  ├── /account              个人资料
  ├── /account/knowledge    个人知识库上传
  ├── /account/resume       个人简历管理
  ├── /account/schedule     课表上传
  └── /login、/register     用户认证

backend: FastAPI（backend/app.py）
  ├── /api/auth             注册 / 登录 / 当前用户
  ├── /api/chat             问答 + 流式 + 会话持久化
  ├── /api/search           RAG / 文档检索
  ├── /api/resources        专业、机构、联系、入口、下载、学术搜索
  ├── /api/upload           用户私有文档
  ├── /api/schedule         课表与今日校园
  ├── /api/resume           简历增强
  ├── /api/interview        模拟面试
  ├── /api/admin            管理（占位）
  ├── /health、/api/stats   健康检查与统计

agent layer（backend/agents/）
  ├── AgentController       主控：取证 → 裁决 → 生成
  ├── QuestionRouter        意图识别，fast / collab
  ├── EvidenceSupervisor    证据优先级（api / tool / rag / document / affairs）
  ├── AnswerGenerator       DeepSeek 回答生成
  └── FallbackHandler       无依据兜底

knowledge layer（backend/rag/ + backend/database/）
  ├── RAGRetriever          官网 / 共享文档 / 用户文档检索
  ├── VectorStore（Chroma） zhku_campus / zhku_documents / zhku_user_docs
  └── MySQL                 结构化表 + 用户表

tools（backend/tools/）
  ├── major_search          MajorTool
  ├── download_search       DownloadTool
  ├── contact_search        ContactTool
  ├── service_link_search   ServiceLinkTool
  ├── weather_search        WeatherTool（和风天气）
  ├── academic_search       AcademicSearchTool
  └── map_route             MapTool（高德地图）

crawler（crawler/）
  ├── run_all.py            采集总入口
  ├── crawl_*.py            分站点爬虫
  ├── parse_documents.py    PDF/DOC/DOCX 解析
  └── build_kb.py           向量库与 DB 构建
```

---

## 6. Agent 工作流

### 6.1 基础流程

```text
用户问题（+ 可选 history / user_id / user_role）
  ↓
QuestionRouter：意图识别 + fast / collab 判定
  ↓
并行 / 串行子 Agent 取证
  ├── general_rag      官网向量检索
  ├── document_rag   用户私有或共享文档检索
  ├── tool           结构化工具或第三方 API
  └── fallback       越界或无命中
  ↓
EvidenceSupervisor：裁决证据优先级并过滤
  ↓
AnswerGenerator：DeepSeek 生成回答（含来源约束）
  ↓
FallbackChecker：无可靠证据时兜底
  ↓
返回答案、sources、attachments、tools_used、confidence
```

### 6.2 路由模式

| 模式 | 触发条件 | 行为 |
|---|---|---|
| **fast** | 单一意图、简单查询 | 单工具或单次 RAG，低延迟 |
| **collab** | 办事流程复合问、多意图连接词、文档+办事组合 | 多工具并行取证，Supervisor 融合 |

### 6.3 意图路由示例

| 用户问题 | 意图 | 工具 / 路径 |
|---|---|---|
| 学校有几个校区？ | 学校概况 | `general_rag` |
| 缓考申请表在哪里下载？ | 教务资料 | `download_search` |
| 白云校区网络报障电话是多少？ | 联系方式 | `contact_search` |
| 数据科学与大数据技术专业在哪个学院？ | 专业查询 | `major_search` |
| VPN 入口在哪里？ | 服务入口 | `service_link_search` |
| 今天要不要带伞？ | 天气 | `weather_search` |
| 从广州南站到白云校区怎么走？ | 路线 | `map_route` |
| 机器学习方向有哪些前沿论文？ | 学术搜索 | `academic_search` |
| 这份培养方案有哪些核心课程？ | 智能文档 | `document_rag`（用户上传） |
| 缓考怎么申请，要找谁，表格在哪？ | 办事协作 | collab：`download_search` + `contact_search` + RAG |
| 学校有没有自动办理所有请假手续的入口？ | 越界 | `fallback` |

### 6.4 结构化工具一览

| 工具名 | 类 | 数据源 |
|---|---|---|
| `major_search` | `MajorTool` | MySQL / metadata |
| `download_search` | `DownloadTool` | MySQL / metadata |
| `contact_search` | `ContactTool` | MySQL / metadata |
| `service_link_search` | `ServiceLinkTool` | MySQL / metadata |
| `weather_search` | `WeatherTool` | 和风天气 API |
| `academic_search` | `AcademicSearchTool` | 学术搜索 API + LLM 关键词优化 |
| `map_route` | `MapTool` | 高德地图 API |

---

## 7. RAG 与智能文档设计

### 7.1 Chroma 向量集合（实际配置）

| 集合名（环境变量） | 用途 |
|---|---|
| `zhku_campus`（`CHROMA_COLLECTION_ZHKU`） | 官网页面、新闻、服务指南等全站 RAG |
| `zhku_documents`（`CHROMA_COLLECTION_DOCUMENT`） | 共享文档（爬虫解析的 PDF 等） |
| `zhku_user_docs`（`CHROMA_COLLECTION_USER_DOCS`） | 用户上传私有文档，按 `user_id` 过滤 |

### 7.2 智能文档能力

| 能力 | 说明 | 状态 |
|---|---|---|
| 文档问答 | 围绕上传文档或共享文档连续提问 | ✅ |
| 文档摘要 | Agent 结合检索片段生成摘要 | ✅ |
| 关键字段抽取 | 通过 Prompt 从片段中抽取 | ✅ |
| 用户私有库 | 登录用户上传 PDF/DOC/DOCX/TXT/MD | ✅ |
| 跨文档对比 | 多文档对比 | ⏳ 部分支持（依赖多文档上传与 collab） |

用户文档检索参数（`.env`）：`RAG_DOC_TOP_K=15`、`RAG_DOC_SCORE_THRESHOLD=0.12`，对小文档会拉取全文片段以提高培养方案类 PDF 的召回。

### 7.3 文档处理流程

```text
采集官网文档入口 / 用户上传
  ↓
parse_documents.parse_file（PyMuPDF / python-docx 等）
  ↓
split_into_chunks（CHUNK_SIZE=500, OVERLAP=50）
  ↓
Embedding（BAAI/bge-small-zh-v1.5 本地模型）
  ↓
写入 Chroma + UserDocument 元数据（MySQL）
  ↓
Agent document_rag 路径检索
```

---

## 8. 数据采集与清洗

### 8.1 采集流程

```text
python -m crawler.run_all [--skip-job]
  ↓
各 crawl_*.py 写入 data/raw/、data/cleaned/、data/metadata/
  ↓
python -m crawler.build_kb
  ↓
切分 → Embedding → Chroma + MySQL seed
```

### 8.2 采集原则

（与 v1.0 一致，略）

优先采集与学生、教师、研究生、考生和访客直接相关的公开信息；不采集登录后数据与他人隐私。

---

## 9. 核心数据模型

### 9.1 校园公开结构化表（MySQL）

见 `backend/database/schema.sql`：

- `school_profile`、`campus`
- `organization`、`major`
- `download_resource`、`service_link`、`contact`
- `news_article`、`job_posting`
- `document`、`document_chunk`、`document_qa_log`

### 9.2 用户与扩展表

| 表名 | 用途 |
|---|---|
| `user` | 用户名、邮箱、角色、密码哈希 |
| `chat_session` / `chat_message` | 登录用户对话持久化 |
| `resume_profile` | 简历 JSON 与可选文件路径 |
| `user_document` | 用户上传文档元数据 |
| `user_schedule`（运行时 create） | 课表 JSON 与文件路径 |
| `campus_weather_cache` / `campus_advice_cache` | 今日校园天气与建议缓存 |

用户文件落盘：`data/users/{user_id}/uploads/`（文档）、课表目录由 `backend/storage/user_files.py` 管理。

---

## 10. 后端 API 设计（当前路由）

> 完整交互式文档：启动后端后访问 `http://localhost:8000/docs`

### 10.1 问答接口

**`POST /api/chat`** — 非流式问答

```json
{
  "question": "缓考申请表在哪里下载？",
  "user_role": "student",
  "session_id": "optional",
  "history": []
}
```

**`POST /api/chat/stream`** — SSE 流式问答

响应字段（与非流式一致）：

```json
{
  "answer": "回答正文",
  "confidence": "high",
  "sources": [{ "title": "", "department": "", "url": "", "publish_date": "", "snippet": "" }],
  "attachments": [{ "name": "", "file_type": "", "source_page_url": "", "file_url": "" }],
  "tools_used": ["download_search"],
  "fallback": false,
  "session_id": null,
  "llm_query_optimization": null
}
```

**会话持久化**（需登录）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/chat/sessions` | 会话列表 |
| POST | `/api/chat/sessions` | 新建会话 |
| DELETE | `/api/chat/sessions/{id}` | 删除会话 |
| GET | `/api/chat/sessions/{id}/messages` | 消息列表 |
| POST | `/api/chat/sessions/{id}/messages` | 批量追加消息 |
| DELETE | `/api/chat/sessions/{id}/messages` | 清空消息 |

### 10.2 检索接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/search/rag?q=` | 官网 RAG 调试检索 |
| GET | `/api/search/documents?q=` | 文档检索（登录用户含私有库） |
| GET | `/api/search/news?q=` | 新闻检索（占位，返回空） |

### 10.3 结构化资源接口

前缀 `/api/resources`：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/majors?keyword=` | 专业查询 |
| GET | `/organizations?keyword=` | 机构查询 |
| GET | `/contacts?keyword=&campus=` | 联系方式 |
| GET | `/service-links?keyword=&role=` | 服务入口 |
| GET | `/downloads?keyword=&category=` | 资料下载 |
| GET | `/academic?q=` | 学术搜索 |
| GET | `/academic/optimize?q=` | 学术关键词 LLM 优化 |
| POST | `/academic/analyze` | 学术结果分析 |

### 10.4 用户认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 登录，返回 JWT |
| GET | `/api/auth/me` | 当前用户（Bearer Token） |

### 10.5 用户私有文档

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/upload` | 上传文档（覆盖写该用户全部私有文档） |
| GET | `/api/upload/docs` | 列出当前用户文档 |
| DELETE | `/api/upload/docs/{doc_id}` | 删除指定文档 |

### 10.6 课表与今日校园

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/schedule/profile` | 获取课表 |
| POST | `/api/schedule/upload` | 上传 Excel 课表 |
| DELETE | `/api/schedule/profile` | 删除课表 |
| GET | `/api/schedule/today` | 今日课程 + 天气 + LLM 建议 |
| GET | `/api/schedule/week` | 周视图数据 |
| GET | `/api/schedule/navigate/locations` | 导航地点列表 |
| POST | `/api/schedule/navigate` | 路线规划 |

### 10.7 简历与模拟面试

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/PUT | `/api/resume/profile` | 简历读写 |
| POST | `/api/resume/upload` | 上传简历文件 |
| POST | `/api/resume/enhance` | LLM 简历增强 |
| POST | `/api/interview/start` | 开始模拟面试 |
| POST | `/api/interview/answer` | 提交回答并评分 |
| POST | `/api/interview/skip` | 跳过并查看参考答案 |
| POST | `/api/interview/answer/stream` | 流式评分 |

### 10.8 管理与元信息

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/api/stats` | 知识库 chunk 统计 |
| POST | `/api/admin/kb/rebuild` | 重建知识库（stub） |
| GET | `/api/admin/links/check` | 链接检测（stub） |
| POST | `/api/admin/crawl/run` | 触发采集（stub） |

---

## 11. 项目目录（当前）

```text
project/
├── backend/
│   ├── app.py                 # FastAPI 入口
│   ├── config.py              # 环境变量配置
│   ├── api/                   # chat, search, resources, auth, upload,
│   │                          # schedule, resume, interview, admin
│   ├── agents/                # controller, router, supervisor,
│   │                          # answer_generator, fallback
│   ├── rag/                   # retriever, embedder, vector_store, prompt_templates
│   ├── tools/                 # 7 个结构化 / API 工具
│   ├── database/              # models, schema.sql, seed, session, migrate
│   ├── auth/                  # JWT、密码哈希、依赖注入
│   ├── services/              # 课表解析、简历、缓存、出行导航
│   └── storage/               # 用户文件路径
├── crawler/
│   ├── run_all.py
│   ├── crawl_zhku_main.py, crawl_jwc.py, crawl_yjs.py, crawl_job.py
│   ├── crawl_services.py, crawl_extra.py, crawl_training_plans.py
│   ├── parse_documents.py, build_kb.py, common.py
├── frontend/
│   ├── src/pages/             # Home, Chat, Downloads, CampusToday, Resume,
│   │                          # Account, Login, Register
│   ├── src/components/        # 课表、导航、知识库、面试聊天等
│   └── package.json
├── analytics/                 # 评测与可视化脚本（可选）
├── data/
│   ├── raw/, cleaned/, metadata/
│   ├── sqlite/                # 旧库迁移源
│   ├── vector_store/          # Chroma 持久化
│   └── users/                 # 用户上传文件
├── docs/
├── requirements.txt
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 12. 推荐技术栈（当前采用）

| 层级 | 采用 |
|---|---|
| 后端 | Python 3.11+ / FastAPI |
| Agent 编排 | 自研 Router + Supervisor（LangChain 调用 DeepSeek） |
| LLM | DeepSeek API（`deepseek-chat` / `deepseek-v4-flash`） |
| Embedding | BAAI/bge-small-zh-v1.5（本地） |
| 向量库 | Chroma |
| 结构化数据库 | **MySQL 8** |
| 全文检索 | InnoDB FULLTEXT（download、news 表） |
| 前端 | **React + Vite** |
| 数据采集 | requests + BeautifulSoup |
| 文档解析 | PyMuPDF / python-docx |
| 第三方 API | 和风天气、高德地图 |
| 部署 | Docker Compose / venv |

---

## 13. 前端页面设计（当前路由）

| 路由 | 页面 | 功能 |
|---|---|---|
| `/` | 首页 | 项目简介、角色入口、常用模块 |
| `/chat` | 智能问答 | 流式聊天、来源、附件、会话侧边栏（登录） |
| `/downloads` | 资料下载 | 教务 / 研究生 / 招生等分类检索 |
| `/campus-today` | 今日校园 | 今日课表、天气、出行建议、周视图、校区导航 |
| `/resume` | 简历中心 | 简历表单、LLM 增强、模拟面试 |
| `/account` | 个人资料 | 显示名、邮箱、角色 |
| `/account/knowledge` | 个人知识库 | 上传 PDF 等供问答检索 |
| `/account/resume` | 个人简历 | 与简历中心数据同步 |
| `/account/schedule` | 我的课表 | Excel 上传与管理 |
| `/login`、`/register` | 认证 | JWT 登录注册 |

问答结果展示顺序：直接答案 → 步骤 / 附件 / 入口 → 来源引用 → 置信度 / 工具名。

---

## 14. Prompt 与回答规则

### 14.1 系统 Prompt 要点

Agent 应遵守：

1. 只基于已采集的仲恺农业工程学院公开资料及用户授权上传文档回答。
2. 优先引用来源，不确定时不回答具体数值。
3. 涉及电话、地点、时间、报销、招生、学籍等事项时必须展示来源。
4. 如果多个来源冲突，提示用户以最新官网页面为准。
5. 如果检索不到可靠资料，触发兜底，不编造。
6. Supervisor 已在结构层过滤证据，AnswerGenerator 仅使用裁决后的 hits。

### 14.2 兜底回答模板

```text
未在当前已采集的仲恺农业工程学院公开资料中找到可靠依据。
为避免提供错误信息，建议你访问对应部门官网或联系学校相关部门确认。
```

---

## 15. 开发路线与完成度

| 阶段 | 产出 | 状态 |
|---|---|---|
| 1. 需求与数据源确认 | MVP 清单、采集页面、演示问题集 | ✅ |
| 2. 数据采集与清洗 | raw / cleaned / metadata | ✅ |
| 3. 知识库与数据库 | MySQL + Chroma + build_kb | ✅ |
| 4. 后端与 Agent | FastAPI、Router、Supervisor、工具、兜底 | ✅ |
| 5. 前端与演示 | React 全站、流式问答、今日校园 | ✅ |
| 6. 用户扩展功能 | 登录、知识库、课表、简历、面试 | ✅ |
| 7. 测试与交付 | 评测脚本、部署文档 | 🔄 进行中 |
| 8. 管理端完善 | Admin 真实触发采集 / 重建 / 链接检测 | ⏳ 待做 |

---

## 16. 测试方案

### 16.1 测试问题分类

（与 v1.0 一致：学校概况、机构学院、专业培养、教务下载、研究生、招生就业、后勤网络医疗、越界问题）

### 16.2 评价指标

| 指标 | 说明 |
|---|---|
| 检索命中率 | Top-K 是否包含正确来源 |
| 回答准确率 | 生成内容与来源是否一致 |
| 引用完整率 | 标题、URL、发布时间 |
| 工具调用准确率 | Router 是否选对工具 |
| 兜底正确率 | 无依据问题是否拒绝编造 |
| 链接有效率 | 来源 URL 是否可访问 |
| 响应速度 | 普通问答与 collab 耗时 |
| 用户体验 | 流式展示、移动端布局 |

可选运行 `analytics/` 下评测脚本进行批量测试。

---

## 17. 主要风险与应对

| 风险 | 应对 |
|---|---|
| 官网结构变化 | 采集器分模块、定期重跑 `run_all` |
| 附件下载受限 | 保存来源页面和附件名，不绕过限制 |
| 信息过期 | 展示发布时间，定期重采集 |
| RAG 误匹配 | metadata 过滤 + Supervisor 证据过滤 |
| 大模型编造 | 强制来源检查与兜底模板 |
| 用户上传恶意文件 | 类型与大小限制、私有集合隔离 |
| 第三方 API 额度 | 天气 / 地图结果缓存（`campus_cache`） |

---

## 18. MVP 演示问题

| 场景 | 示例问题 | 展示能力 |
|---|---|---|
| 学校概况 | 仲恺农业工程学院有几个校区？ | RAG + 来源 |
| 机构导航 | 学校有哪些教学机构？ | 结构化查询 |
| 专业查询 | 数据科学与大数据技术专业培养方案在哪里？ | major_search + 文档 |
| 教务资料 | 补办学生证申请表在哪里？ | download_search |
| 研究生服务 | 研究生免修课程申请表在哪里？ | download_search |
| 后勤联系 | 后勤维修科电话是多少？ | contact_search |
| 网络服务 | 白云校区网络报障电话是多少？ | contact_search |
| 校医院 | 去校医院看病需要带什么？ | RAG |
| 天气 | 今天广州会下雨吗？ | weather_search |
| 路线 | 从海珠校区到白云校区怎么走？ | map_route |
| 学术 | 推荐几篇关于智慧农业的论文 | academic_search |
| 个人文档 | （先上传培养方案 PDF）这门专业有哪些必修课？ | document_rag |
| 今日校园 | （登录并上传课表）今天有什么课？ | schedule + 天气 |
| 兜底 | 学校有没有自动办理所有请假手续的入口？ | fallback |

---

## 19. 开发优先级（更新）

### P0：已完成

- FastAPI 后端、DeepSeek、RAG、MySQL、7 个工具、兜底、React 问答页

### P1：已完成 / 进行中

- ✅ 智能文档与用户知识库  
- ✅ 资料下载中心、服务入口  
- ✅ 流式输出与会话持久化  
- ✅ 今日校园、简历、模拟面试  
- ⏳ Admin 真实任务触发、链接检测  

### P2：可选增强

- 新闻公告独立检索 API  
- 多文档对比 UI  
- 就业职位结构化深度检索  
- 用户反馈统计  
- LangGraph 可视化编排  
- 生产环境 CI/CD  

---

## 20. 快速开始

### 环境准备

```bash
cd project
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # 填入 DEEPSEEK_API_KEY、MySQL、可选 QWEATHER / AMAP
```

### 初始化数据库

```bash
python -m backend.database.seed
# 若有旧 SQLite：自动迁移，不删除原文件
```

### 采集与建库（可选，若 data 已有可跳过）

```bash
python -m crawler.run_all
python -m crawler.build_kb
```

### 启动服务

```bash
# 后端
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

# 前端（新终端）
cd frontend && npm install && npm run dev
```

### Docker

```bash
docker compose up --build
```

访问：前端 `http://localhost:5173`，API 文档 `http://localhost:8000/docs`。

---

## 21. 关键环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API |
| `MYSQL_*` | 是 | MySQL 连接 |
| `QWEATHER_API_KEY` / `QWEATHER_API_HOST` | 否 | 天气工具 |
| `AMAP_API_KEY` | 否 | 路线规划 |
| `JWT_SECRET_KEY` | 生产必填 | 用户认证 |
| `EMBEDDING_MODEL` | 否 | 默认 bge-small-zh |
| `AGENT_ROUTER_MODE` | 否 | `rule`（默认）或 `llm` |

完整列表见项目根目录 `.env.example`。

---

## 22. 项目结论

ZHKU Campus Agent 当前实现方向：

> 用 FastAPI 搭建后端，用 Router + Supervisor 编排多 Agent，用 DeepSeek API 生成回答，用官网公开资料与用户授权文档构建 Chroma 向量库，用 MySQL 保存结构化校园数据与用户扩展数据，通过 React 前端提供可追溯、可引用、不编造的校园信息服务，并扩展今日校园、简历与模拟面试等智慧生活场景。

可靠闭环：

```text
用户自然语言提问（可选登录与个人上下文）
  ↓
Router 判断 fast / collab 与意图
  ↓
RAG / 文档 / 结构化工具 / 第三方 API 并行取证
  ↓
Supervisor 裁决证据优先级
  ↓
DeepSeek 生成带来源的回答
  ↓
前端展示答案、附件、服务入口与流式体验
```

---

*文档版本 v2.0-dev · 与仓库 `backend/`、`frontend/`、`crawler/` 实现对齐 · 如有接口变更请以 `http://localhost:8000/docs` 为准。*
