-- ZHKU Campus Agent 数据库 Schema（MySQL 8）
-- 由原 SQLite schema 迁移而来；全文检索改用 InnoDB FULLTEXT

CREATE TABLE IF NOT EXISTS school_profile (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    history TEXT,
    campus_summary TEXT,
    phone VARCHAR(64),
    source_url VARCHAR(512),
    updated_at DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS campus (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    address VARCHAR(256),
    phone VARCHAR(64),
    map_url VARCHAR(512),
    image_url VARCHAR(512),
    source_url VARCHAR(512)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS organization (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    type VARCHAR(64),
    website_url VARCHAR(512),
    parent_id INT NULL,
    source_url VARCHAR(512),
    updated_at DATETIME NULL,
    INDEX idx_organization_type (type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS major (
    id INT AUTO_INCREMENT PRIMARY KEY,
    major_code VARCHAR(32),
    major_name VARCHAR(128) NOT NULL,
    college_name VARCHAR(128),
    discipline_category VARCHAR(64),
    degree_category VARCHAR(64),
    training_plan_url VARCHAR(512),
    source_url VARCHAR(512),
    updated_at DATETIME NULL,
    INDEX idx_major_name (major_name),
    INDEX idx_major_code (major_code),
    INDEX idx_major_college (college_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS download_resource (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(256) NOT NULL,
    category VARCHAR(64),
    audience VARCHAR(32),
    file_type VARCHAR(16),
    source_page_url VARCHAR(512),
    file_url VARCHAR(512),
    publish_date VARCHAR(32),
    department VARCHAR(128),
    keywords VARCHAR(256),
    crawl_time DATETIME NULL,
    is_public INT DEFAULT 1,
    download_note TEXT,
    INDEX idx_download_title (title),
    INDEX idx_download_category (category),
    FULLTEXT INDEX ft_download_title_keywords (title, keywords)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS service_link (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    category VARCHAR(64),
    url VARCHAR(512),
    requires_login INT DEFAULT 0,
    user_role VARCHAR(32),
    description TEXT,
    source_url VARCHAR(512),
    INDEX idx_service_link_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS contact (
    id INT AUTO_INCREMENT PRIMARY KEY,
    department VARCHAR(128) NOT NULL,
    office_name VARCHAR(128),
    campus VARCHAR(32),
    service_scope TEXT,
    phone VARCHAR(64),
    address VARCHAR(256),
    source_url VARCHAR(512),
    updated_at DATETIME NULL,
    INDEX idx_contact_department (department)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS news_article (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(256) NOT NULL,
    category VARCHAR(64),
    department VARCHAR(128),
    publish_date VARCHAR(32),
    source_url VARCHAR(512),
    summary TEXT,
    content TEXT,
    crawl_time DATETIME NULL,
    INDEX idx_news_title (title),
    INDEX idx_news_category (category),
    INDEX idx_news_publish_date (publish_date),
    FULLTEXT INDEX ft_news_title_content (title, content)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS job_posting (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(256) NOT NULL,
    company VARCHAR(128),
    publish_date VARCHAR(32),
    salary_range VARCHAR(64),
    education_requirement VARCHAR(64),
    industry VARCHAR(64),
    location VARCHAR(64),
    source_url VARCHAR(512),
    crawl_time DATETIME NULL,
    INDEX idx_job_title (title)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(256) NOT NULL,
    department VARCHAR(128),
    category VARCHAR(64),
    source_page_url VARCHAR(512),
    file_url VARCHAR(512),
    file_type VARCHAR(16),
    publish_date VARCHAR(32),
    summary TEXT,
    tags VARCHAR(256),
    parse_status VARCHAR(32) DEFAULT 'pending',
    created_at DATETIME NULL,
    INDEX idx_document_title (title),
    INDEX idx_document_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_chunk (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT,
    section_title VARCHAR(256),
    page_number INT NULL,
    chunk_text TEXT,
    embedding_id VARCHAR(64),
    token_count INT NULL,
    chunk_index INT NULL,
    INDEX idx_chunk_document_id (document_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_qa_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    document_id INT NULL,
    question TEXT,
    retrieved_chunks TEXT,
    answer TEXT,
    created_at DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL,
    email VARCHAR(128),
    password_hash VARCHAR(128) NOT NULL,
    display_name VARCHAR(64),
    role VARCHAR(32) DEFAULT 'student',
    is_active INT DEFAULT 1,
    created_at DATETIME NULL,
    updated_at DATETIME NULL,
    UNIQUE KEY uk_user_username (username),
    UNIQUE KEY uk_user_email (email),
    INDEX idx_user_username (username),
    INDEX idx_user_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chat_session (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(256) DEFAULT '新对话',
    created_at DATETIME NULL,
    updated_at DATETIME NULL,
    INDEX idx_chat_session_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chat_message (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    meta TEXT,
    created_at DATETIME NULL,
    INDEX idx_chat_message_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS resume_profile (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    data TEXT NOT NULL,
    file_path VARCHAR(512),
    updated_at DATETIME NULL,
    UNIQUE KEY uk_resume_user (user_id),
    INDEX idx_resume_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_document (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    doc_id VARCHAR(64) NOT NULL,
    title VARCHAR(256) NOT NULL,
    filename VARCHAR(256),
    file_path VARCHAR(512),
    department VARCHAR(128) DEFAULT '文档库',
    file_type VARCHAR(16),
    size INT DEFAULT 0,
    page_count INT DEFAULT 0,
    chunk_count INT DEFAULT 0,
    created_at DATETIME NULL,
    UNIQUE KEY uk_user_document_doc_id (doc_id),
    INDEX idx_user_document_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
