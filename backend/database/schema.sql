-- ZHKU Campus Agent 数据库 Schema
-- 对应 ZHKU_Campus_Agent.md 第 13.1 节核心表设计

-- 学校概况
CREATE TABLE IF NOT EXISTS school_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    history TEXT,
    campus_summary TEXT,
    phone TEXT,
    source_url TEXT,
    updated_at TIMESTAMP
);

-- 校区信息
CREATE TABLE IF NOT EXISTS campus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT,
    phone TEXT,
    map_url TEXT,
    image_url TEXT,
    source_url TEXT
);

-- 机构设置
CREATE TABLE IF NOT EXISTS organization (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT,                       -- 党政管理机构 / 教学机构 / 教辅科研机构 / 服务平台 / 群团组织
    website_url TEXT,
    parent_id INTEGER,
    source_url TEXT,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_organization_type ON organization(type);

-- 本科专业
CREATE TABLE IF NOT EXISTS major (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    major_code TEXT,
    major_name TEXT NOT NULL,
    college_name TEXT,
    discipline_category TEXT,
    degree_category TEXT,
    training_plan_url TEXT,
    source_url TEXT,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_major_name ON major(major_name);
CREATE INDEX IF NOT EXISTS idx_major_code ON major(major_code);
CREATE INDEX IF NOT EXISTS idx_major_college ON major(college_name);

-- 资料下载
CREATE TABLE IF NOT EXISTS download_resource (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT,                   -- 学生下载 / 学籍学位 / 考务 / 教材 / 课程建设 / 培养方案 / 研究生培养
    audience TEXT,                   -- 学生 / 教师 / 教务人员
    file_type TEXT,                  -- pdf / doc / docx / xls / xlsx / zip
    source_page_url TEXT,
    file_url TEXT,
    publish_date TEXT,
    department TEXT,
    keywords TEXT,
    crawl_time TIMESTAMP,
    is_public INTEGER DEFAULT 1,
    download_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_download_title ON download_resource(title);
CREATE INDEX IF NOT EXISTS idx_download_category ON download_resource(category);

-- 服务入口
CREATE TABLE IF NOT EXISTS service_link (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,                   -- 教务 / 科研 / 行政 / 后勤 / 网络 / 医疗 / 招采 / 就业
    url TEXT,
    requires_login INTEGER DEFAULT 0,
    user_role TEXT,                  -- 学生 / 教师 / 管理人员 / 用人单位 / 访客
    description TEXT,
    source_url TEXT
);
CREATE INDEX IF NOT EXISTS idx_service_link_category ON service_link(category);

-- 部门联系方式
CREATE TABLE IF NOT EXISTS contact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    department TEXT NOT NULL,
    office_name TEXT,
    campus TEXT,                     -- 白云 / 海珠
    service_scope TEXT,
    phone TEXT,
    address TEXT,
    source_url TEXT,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_contact_department ON contact(department);

-- 新闻公告
CREATE TABLE IF NOT EXISTS news_article (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT,                   -- 学校要闻 / 校园快讯 / 通知公告 / 媒体仲恺 / 学术科研
    department TEXT,
    publish_date TEXT,
    source_url TEXT,
    summary TEXT,
    content TEXT,
    crawl_time TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_news_title ON news_article(title);
CREATE INDEX IF NOT EXISTS idx_news_category ON news_article(category);
CREATE INDEX IF NOT EXISTS idx_news_publish_date ON news_article(publish_date);

-- 职位信息
CREATE TABLE IF NOT EXISTS job_posting (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    company TEXT,
    publish_date TEXT,
    salary_range TEXT,
    education_requirement TEXT,
    industry TEXT,
    location TEXT,
    source_url TEXT,
    crawl_time TIMESTAMP
);

-- 智能文档元数据
CREATE TABLE IF NOT EXISTS document (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    department TEXT,
    category TEXT,
    source_page_url TEXT,
    file_url TEXT,
    file_type TEXT,
    publish_date TEXT,
    summary TEXT,
    tags TEXT,
    parse_status TEXT DEFAULT 'pending',
    created_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_document_title ON document(title);
CREATE INDEX IF NOT EXISTS idx_document_category ON document(category);

-- 文档切片
CREATE TABLE IF NOT EXISTS document_chunk (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER,
    section_title TEXT,
    page_number INTEGER,
    chunk_text TEXT,
    embedding_id TEXT,
    token_count INTEGER,
    chunk_index INTEGER
);
CREATE INDEX IF NOT EXISTS idx_chunk_document_id ON document_chunk(document_id);

-- 文档问答日志
CREATE TABLE IF NOT EXISTS document_qa_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER,
    question TEXT,
    retrieved_chunks TEXT,           -- JSON
    answer TEXT,
    created_at TIMESTAMP
);

-- 全文检索（SQLite FTS5）
CREATE VIRTUAL TABLE IF NOT EXISTS news_article_fts USING fts5(
    title, content, content='news_article', content_rowid='id'
);

CREATE VIRTUAL TABLE IF NOT EXISTS download_resource_fts USING fts5(
    title, keywords, content='download_resource', content_rowid='id'
);
