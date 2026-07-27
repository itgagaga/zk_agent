# ZHKU Campus Agent 仲恺校园信息服务智能体

> 基于仲恺农业工程学院公开网站信息构建的校园信息服务智能体，面向学生、教师和访客提供学校信息问答、办事资料检索、服务入口导航和可信来源展示。

## 项目定位

ZHKU Campus Agent 是一个以 Agent 为核心调度器、以 RAG 和智能文档为知识底座、以学校官网公开资料为数据来源的校园信息服务智能体系统。

- **数据来源**：https://www.zhku.edu.cn/ 及公开二级站点
- **核心能力**：Agent 主控 + 意图识别 + RAG + 智能文档 + 结构化工具查询 + 来源引用 + 无依据兜底

## 技术栈

| 层级 | 技术 |
|---|---|
| 后端 | Python + FastAPI |
| 智能体编排 | LangChain / LangGraph |
| 大模型 | DeepSeek API |
| Embedding | bge-small-zh / bge-m3 |
| 向量数据库 | Chroma |
| 结构化数据库 | MySQL |
| 前端 | React + Vite |
| 数据采集 | requests + BeautifulSoup / Playwright |
| 文档解析 | pymupdf / pdfplumber / python-docx |

## 项目结构

```text
zhku-campus-agent/
├── backend/                # FastAPI 后端
│   ├── api/                # API 路由层
│   ├── agents/             # Agent 主控与路由
│   ├── rag/                # RAG 检索模块
│   ├── tools/              # 结构化工具
│   └── database/           # 数据库模型
├── crawler/                # 数据采集与知识库构建
├── frontend/               # 前端 Web 界面
├── data/                   # 数据存储
│   ├── raw/                # 原始采集数据
│   ├── cleaned/            # 清洗后文本
│   ├── metadata/           # 元数据
│   ├── sqlite/             # 旧 SQLite（迁移源，可保留）
│   └── vector_store/       # 向量库
├── docs/                   # 项目文档
├── README.md
├── requirements.txt
├── docker-compose.yml
└── .env.example
```

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
cd zhku-campus-agent

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入 DeepSeek API Key 等配置
```

### 3. 初始化数据库（MySQL）

确保本机 MySQL 已启动，并在 `.env` 中配置 `MYSQL_*`。若仍有旧的 `data/sqlite/zhku.db`，seed 会自动迁入且不删除原文件。

```bash
python -m backend.database.seed
# 也可单独执行迁移：
# python -m backend.database.migrate_sqlite_to_mysql
```

### 4. 启动后端服务

```bash
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

## MVP 演示问题

| 场景 | 示例问题 | 展示能力 |
|---|---|---|
| 学校概况 | 仲恺农业工程学院有几个校区？ | RAG + 来源引用 |
| 机构导航 | 学校有哪些教学机构？ | 结构化查询 |
| 专业查询 | 数据科学与大数据技术专业培养方案在哪里？ | 专业工具 + 附件入口 |
| 教务资料 | 补办学生证申请表在哪里？ | 下载资源工具 |
| 后勤联系 | 后勤维修科电话是多少？ | 联系方式工具 |

## 文档

- [项目说明](docs/ZHKU_Campus_Agent.md)
- [开发顺序建议](docs/仲恺校园信息服务智能体_开发顺序建议.md)
- [设计规范](backend/docs/DESIGN-mastercard.md)
