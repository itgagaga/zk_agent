# ZHKU Campus Agent 仲恺校园信息服务智能体

> 面向仲恺农业工程学院学生、教师和访客的校园信息服务平台：用一个入口连接校园公开知识、办事资源、实时服务与个人资料，并为回答提供可追溯来源。

## 项目简介

ZHKU Campus Agent 以 Agent 为统一调度入口，以校园官网、公开二级站点、共享文档和用户个人文档为知识来源，提供智能问答、资料检索、服务导航、校园日程与毕业发展支持。

系统当前的问答主链路为：

```text
用户问题
  → Query Planner（理解问题、拆分子问题、选择知识范围与工具）
  → Retrieval Manager（并行检索官网、共享文档、个人文档和结构化工具）
  → BM25 + 向量召回 + RRF 融合
  → Evidence Gate（证据充分性判断与边界控制）
  → Answer Generator（生成回答、来源引用与检索摘要）
  → 无依据兜底
```

## 核心功能

| 模块 | 能力 |
|---|---|
| 智能问答 | 多轮会话、SSE 流式输出、问题规划、混合检索、来源引用、检索摘要与无依据兜底 |
| 知识范围 | 标准模式（校园公开资料与平台工具）、增强模式（加入个人知识库）、私有模式（仅个人知识库） |
| 资料智库 | 专业、机构、联系方式、服务入口、下载资料、就业信息和学术资源检索 |
| 个人知识库 | 用户文档上传、解析、向量化、隔离检索与文档管理 |
| 校园今日 | Excel 课表导入、今日课程、天气、出行建议、地点查询与路线规划 |
| 毕业发展 | 简历档案、简历文件解析与润色、模拟面试、学术搜索及就业信息 |
| 用户系统 | 注册、登录、JWT 鉴权、个人资料与会话历史管理 |
| 管理与评测 | 知识库重建、采集任务、链接检查、RAG/路由/延迟统计评测与可视化报告 |

当前内置 9 类结构化工具：专业、下载资源、联系方式、服务入口、天气、学术搜索、地图路线、就业信息和校园新闻。

## 技术栈

| 层级 | 技术 |
|---|---|
| 后端 | Python 3.13+、FastAPI、Pydantic、SQLAlchemy |
| Agent 与模型 | 自定义 Agent 编排、LangChain、DeepSeek API |
| 检索 | BGE Embedding、Chroma、中文 BM25、RRF 融合、Evidence Gate |
| 数据库与缓存 | MySQL、Redis（可降级问答缓存） |
| 前端 | React 18、Vite 5、React Router、Axios、React Markdown |
| 数据与文档 | requests、BeautifulSoup、trafilatura、PyMuPDF、pdfplumber、python-docx、pandas |
| 测试与分析 | pytest、Node.js Test Runner、matplotlib、Bootstrap/Wilson 区间等统计方法 |

项目保留了 LangGraph 依赖供后续编排扩展；当前生产链路由 `backend/agents/` 与 `backend/rag/` 中的轻量编排实现。

## 项目结构

```text
zhku-campus-agent/
├── backend/
│   ├── agents/             # Agent Controller、回答生成与兜底
│   ├── api/                # 鉴权、问答、检索、上传、课表、简历和面试 API
│   ├── auth/               # bcrypt 密码哈希与 JWT 鉴权
│   ├── cache/              # Redis 索引 + JSON 文件问答缓存
│   ├── database/           # MySQL 模型、Schema、种子数据与 SQLite 迁移
│   ├── rag/                # 规划、召回、融合、证据门控与向量库
│   ├── services/           # 课表、简历、校园今日和路线服务
│   ├── storage/            # 用户文件隔离存储
│   └── tools/              # 9 类结构化查询工具
├── crawler/                # 官网采集、文档处理、分类索引与知识库构建
├── frontend/               # React + Vite Web 应用
├── analytics/              # 竞赛指标计算、统计检验和报告生成
├── data/
│   ├── raw/                # 原始采集数据（默认不提交）
│   ├── cleaned/            # 清洗后文本（默认不提交）
│   ├── metadata/           # 来源与分类元数据（默认不提交）
│   ├── indexes/            # 功能分类索引
│   ├── qa_answers/         # 问答文件缓存
│   ├── sqlite/             # 旧 SQLite 迁移源
│   ├── users/              # 用户私有文件（默认不提交）
│   └── vector_store/       # Chroma 持久化数据（默认不提交）
├── docs/                   # 开发说明、实施计划与评测报告
├── PlantUML/               # 架构图、流程图和时序图源文件
├── .env.example            # 环境变量模板
├── pyproject.toml
└── requirements.txt
```

## 快速开始

### 1. 环境要求

- Python 3.13+
- Node.js 18+
- MySQL
- Redis（可选；不可用时问答缓存自动降级，不影响主问答流程）
- DeepSeek API Key

首次使用本地 Embedding 时需要下载 Hugging Face 模型，耗时取决于网络和设备性能。

### 2. 安装后端依赖

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS/Linux 激活虚拟环境：

```bash
source .venv/bin/activate
```

### 3. 配置环境变量

PowerShell：

```powershell
Copy-Item .env.example .env
```

macOS/Linux：

```bash
cp .env.example .env
```

至少检查以下配置：

| 配置 | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `MYSQL_*` | MySQL 地址、账号、密码与数据库名 |
| `JWT_SECRET_KEY` | 生产环境必须替换为高强度随机字符串 |
| `REDIS_URL` | Redis 连接；不使用时可设置 `QA_CACHE_ENABLED=false` |
| `QWEATHER_*` | 校园天气能力，可选 |
| `AMAP_API_KEY` | 地点搜索与路线规划，可选 |

完整配置及默认值见 [`.env.example`](.env.example)。

### 4. 初始化 MySQL

确保 MySQL 已启动，然后执行：

```powershell
python -m backend.database.seed
```

该命令会创建数据库表；若存在 `data/sqlite/zhku.db`，还会迁移旧数据并保留原文件。

### 5. 准备校园知识库

已有 `data/cleaned/` 和对应 metadata 时，可直接构建：

```powershell
python -m crawler.build_kb
```

需要从公开站点重新采集时：

```powershell
python -m crawler.run_all
python -m crawler.build_kb
```

就业站点采集较慢，可使用 `python -m crawler.run_all --skip-job` 跳过。

### 6. 启动后端

```powershell
python backend/app.py
```

也可以直接使用 Uvicorn：

```powershell
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

启动后可访问：

- API 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/health>

若启用了本地 Embedding 启动预热，服务会在模型就绪后开始接受请求；可通过 `/health` 查看预热与缓存状态。

### 7. 启动前端

另开终端执行：

```powershell
cd frontend
npm install
npm run dev
```

访问 <http://localhost:5173>。开发服务器会把 `/api` 请求代理到 `http://localhost:8000`。

## 测试与构建

后端与统计测试：

```powershell
pip install pytest
python -m pytest backend/tests analytics/tests
```

前端测试与生产构建：

```powershell
cd frontend
npm test
npm run build
```



## 数据与安全说明

- 校园回答以公开来源、已上传文档和结构化工具结果为依据；证据不足时进入兜底，不应凭常识补全校务事实。
- 用户上传文件存放在 `data/users/`，个人向量数据按用户范围过滤；这些目录默认被 Git 忽略。
- `.env`、数据库密码、API Key、JWT 密钥以及真实用户资料不得提交到仓库。
- Redis 仅保存问题到答案分类的运行时映射，答案正文保存在统一 JSON 文件中；缓存不可用时系统继续走正常生成链路。

## 项目文档

- [开发说明](docs/ZHKU_Campus_Agent_开发.md)
- [竞赛统计评测工具](analytics/COMPETITION_ANALYTICS.md)
- `docs/competition-analytics/competition_report.md`（运行评测命令后生成）
- [个人知识范围设计](docs/personal-knowledge-scope.puml)
- [架构图与时序图](PlantUML/)
