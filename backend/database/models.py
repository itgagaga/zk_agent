"""SQLAlchemy 数据模型定义。

对应 ZHKU_Campus_Agent.md 第 13.1 节的核心表设计。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 2.x 声明式基类。"""


class SchoolProfile(Base):
    """学校概况。"""

    __tablename__ = "school_profile"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    description = Column(Text)
    history = Column(Text)
    campus_summary = Column(Text)
    phone = Column(String(64))
    source_url = Column(String(512))
    updated_at = Column(DateTime, default=datetime.utcnow)


class Campus(Base):
    """校区信息。"""

    __tablename__ = "campus"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    address = Column(String(256))
    phone = Column(String(64))
    map_url = Column(String(512))
    image_url = Column(String(512))
    source_url = Column(String(512))


class Organization(Base):
    """机构设置。"""

    __tablename__ = "organization"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    type = Column(String(64))  # 党政管理机构 / 教学机构 / 教辅科研机构 / 服务平台 / 群团组织
    website_url = Column(String(512))
    parent_id = Column(Integer)
    source_url = Column(String(512))
    updated_at = Column(DateTime, default=datetime.utcnow)


class Major(Base):
    """本科专业。"""

    __tablename__ = "major"

    id = Column(Integer, primary_key=True, autoincrement=True)
    major_code = Column(String(32), index=True)
    major_name = Column(String(128), nullable=False, index=True)
    college_name = Column(String(128), index=True)
    discipline_category = Column(String(64))
    degree_category = Column(String(64))
    training_plan_url = Column(String(512))
    source_url = Column(String(512))
    updated_at = Column(DateTime, default=datetime.utcnow)


class DownloadResource(Base):
    """资料下载。"""

    __tablename__ = "download_resource"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False, index=True)
    category = Column(String(64), index=True)
    audience = Column(String(32))
    file_type = Column(String(16))
    source_page_url = Column(String(512))
    file_url = Column(String(512))
    publish_date = Column(String(32))
    department = Column(String(128))
    keywords = Column(String(256))
    crawl_time = Column(DateTime, default=datetime.utcnow)
    is_public = Column(Integer, default=1)
    download_note = Column(Text)


class ServiceLink(Base):
    """服务入口。"""

    __tablename__ = "service_link"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    category = Column(String(64), index=True)
    url = Column(String(512))
    requires_login = Column(Integer, default=0)
    user_role = Column(String(32))
    description = Column(Text)
    source_url = Column(String(512))


class Contact(Base):
    """部门联系方式。"""

    __tablename__ = "contact"

    id = Column(Integer, primary_key=True, autoincrement=True)
    department = Column(String(128), nullable=False, index=True)
    office_name = Column(String(128))
    campus = Column(String(32))
    service_scope = Column(Text)
    phone = Column(String(64))
    address = Column(String(256))
    source_url = Column(String(512))
    updated_at = Column(DateTime, default=datetime.utcnow)


class NewsArticle(Base):
    """新闻公告。"""

    __tablename__ = "news_article"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False, index=True)
    category = Column(String(64), index=True)
    department = Column(String(128))
    publish_date = Column(String(32), index=True)
    source_url = Column(String(512))
    summary = Column(Text)
    content = Column(Text)
    crawl_time = Column(DateTime, default=datetime.utcnow)


class JobPosting(Base):
    """职位信息。"""

    __tablename__ = "job_posting"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False, index=True)
    company = Column(String(128))
    publish_date = Column(String(32))
    salary_range = Column(String(64))
    education_requirement = Column(String(64))
    industry = Column(String(64))
    location = Column(String(64))
    source_url = Column(String(512))
    crawl_time = Column(DateTime, default=datetime.utcnow)


class Document(Base):
    """智能文档元数据。"""

    __tablename__ = "document"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False, index=True)
    department = Column(String(128))
    category = Column(String(64), index=True)
    source_page_url = Column(String(512))
    file_url = Column(String(512))
    file_type = Column(String(16))
    publish_date = Column(String(32))
    summary = Column(Text)
    tags = Column(String(256))
    parse_status = Column(String(32), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


class DocumentChunk(Base):
    """文档切片。"""

    __tablename__ = "document_chunk"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, index=True)
    section_title = Column(String(256))
    page_number = Column(Integer)
    chunk_text = Column(Text)
    embedding_id = Column(String(64))
    token_count = Column(Integer)
    chunk_index = Column(Integer)


class User(Base):
    """系统用户（登录注册）。"""

    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, unique=True, index=True)
    email = Column(String(128), unique=True, index=True)
    password_hash = Column(String(128), nullable=False)
    display_name = Column(String(64))
    role = Column(String(32), default="student")  # student / teacher / admin
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatSession(Base):
    """用户聊天会话。"""

    __tablename__ = "chat_session"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    title = Column(String(256), default="新对话")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessage(Base):
    """聊天消息。"""

    __tablename__ = "chat_message"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, nullable=False, index=True)
    role = Column(String(16), nullable=False)  # user / assistant
    content = Column(Text, nullable=False, default="")
    meta = Column(Text)  # JSON 字符串：sources 等
    created_at = Column(DateTime, default=datetime.utcnow)


class ResumeProfile(Base):
    """用户简历（每人一份）。"""

    __tablename__ = "resume_profile"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, unique=True, index=True)
    data = Column(Text, nullable=False, default="{}")  # JSON
    file_path = Column(String(512))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserDocument(Base):
    """用户私有智能文档元数据。"""

    __tablename__ = "user_document"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    doc_id = Column(String(64), nullable=False, unique=True, index=True)
    title = Column(String(256), nullable=False)
    filename = Column(String(256))
    file_path = Column(String(512))
    department = Column(String(128), default="文档库")
    file_type = Column(String(16))
    size = Column(Integer, default=0)
    page_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
