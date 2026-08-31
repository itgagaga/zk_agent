"""ZHKU Campus Agent 后端应用配置。

所有配置项从环境变量读取，统一通过 Settings 类暴露。
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """应用配置。从项目根目录 .env 读取，不依赖启动时的 cwd。"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.is_file() else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 大模型
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL"
    )
    deepseek_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL")

    # Embedding
    embedding_model: str = Field(
        default="BAAI/bge-small-zh-v1.5", alias="EMBEDDING_MODEL"
    )
    embedding_provider: Literal["local", "openai", "dashscope"] = Field(
        default="local", alias="EMBEDDING_PROVIDER"
    )

    # 向量库
    vector_store_type: Literal["chroma", "faiss"] = Field(
        default="chroma", alias="VECTOR_STORE_TYPE"
    )
    vector_store_path: Path = Field(
        default=DATA_DIR / "vector_store", alias="VECTOR_STORE_PATH"
    )
    chroma_collection_zhku: str = Field(
        default="zhku_campus", alias="CHROMA_COLLECTION_ZHKU"
    )
    chroma_collection_document: str = Field(
        default="zhku_documents", alias="CHROMA_COLLECTION_DOCUMENT"
    )
    chroma_collection_user_docs: str = Field(
        default="zhku_user_docs", alias="CHROMA_COLLECTION_USER_DOCS"
    )

    # MySQL
    mysql_host: str = Field(default="127.0.0.1", alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, alias="MYSQL_PORT")
    mysql_user: str = Field(default="root", alias="MYSQL_USER")
    mysql_password: str = Field(default="", alias="MYSQL_PASSWORD")
    mysql_database: str = Field(default="zhku", alias="MYSQL_DATABASE")
    mysql_charset: str = Field(default="utf8mb4", alias="MYSQL_CHARSET")

    # 旧 SQLite 路径（仅用于一次性迁移，业务读写已切到 MySQL）
    sqlite_path: Path = Field(default=DATA_DIR / "sqlite" / "zhku.db", alias="SQLITE_PATH")

    @property
    def database_url(self) -> str:
        """SQLAlchemy MySQL 连接串。"""
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset={self.mysql_charset}"
        )

    # 第三方 API
    qweather_api_key: str = Field(default="", alias="QWEATHER_API_KEY")
    qweather_api_host: str = Field(
        default="",
        alias="QWEATHER_API_HOST",
        description="和风天气独立 API Host，如 xxx.qweatherapi.com（控制台-设置中查看）",
    )
    qweather_credential_id: str = Field(
        default="", alias="QWEATHER_CREDENTIAL_ID"
    )
    amap_api_key: str = Field(default="", alias="AMAP_API_KEY")

    # 采集源
    zhku_base_url: str = Field(default="https://www.zhku.edu.cn/", alias="ZHKU_BASE_URL")
    zhku_jwc_url: str = Field(
        default="https://jwc.zhku.edu.cn/", alias="ZHKU_JWC_URL"
    )
    zhku_yjs_url: str = Field(
        default="https://yjs.zhku.edu.cn/", alias="ZHKU_YJS_URL"
    )
    zhku_job_url: str = Field(
        default="https://job.zhku.edu.cn/", alias="ZHKU_JOB_URL"
    )
    zhku_hqyzc_url: str = Field(
        default="https://hqyzc.zhku.edu.cn/", alias="ZHKU_HQYZC_URL"
    )
    zhku_wlzx_url: str = Field(
        default="https://wlzx.zhku.edu.cn/", alias="ZHKU_WLZX_URL"
    )
    zhku_xys_url: str = Field(
        default="https://xys.zhku.edu.cn/", alias="ZHKU_XYS_URL"
    )

    crawl_delay: float = Field(default=1.0, alias="CRAWL_DELAY")
    crawl_timeout: int = Field(default=15, alias="CRAWL_TIMEOUT")
    crawl_user_agent: str = Field(
        default="ZHKU-Campus-Agent/0.1 (+https://www.zhku.edu.cn/)",
        alias="CRAWL_USER_AGENT",
    )

    # RAG 切分：结构优先 + Parent-Child
    chunk_size: int = Field(
        default=600,
        alias="CHUNK_SIZE",
        description="Child 目标长度（字符）；Parent 超长时在节内递归切分",
    )
    chunk_overlap: int = Field(default=80, alias="CHUNK_OVERLAP")
    chunk_min_size: int = Field(default=80, alias="CHUNK_MIN_SIZE")
    parent_max_size: int = Field(default=1500, alias="PARENT_MAX_SIZE")
    short_doc_max_size: int = Field(default=800, alias="SHORT_DOC_MAX_SIZE")
    campus_chunk_size: int = Field(default=600, alias="CAMPUS_CHUNK_SIZE")
    campus_chunk_overlap: int = Field(default=80, alias="CAMPUS_CHUNK_OVERLAP")
    campus_parent_max_size: int = Field(default=1500, alias="CAMPUS_PARENT_MAX_SIZE")
    document_chunk_size: int = Field(default=600, alias="DOCUMENT_CHUNK_SIZE")
    document_chunk_overlap: int = Field(default=80, alias="DOCUMENT_CHUNK_OVERLAP")
    document_parent_max_size: int = Field(default=1500, alias="DOCUMENT_PARENT_MAX_SIZE")
    kb_schema_version: str = Field(default="rag-evidence-v2", alias="KB_SCHEMA_VERSION")
    rag_top_k: int = Field(default=5, alias="RAG_TOP_K")
    rag_score_threshold: float = Field(default=0.5, alias="RAG_SCORE_THRESHOLD")
    # 用户上传文档检索：阈值更低、召回更多，培养方案类 PDF 常分散在多个片段
    rag_doc_top_k: int = Field(default=15, alias="RAG_DOC_TOP_K")
    rag_doc_score_threshold: float = Field(default=0.12, alias="RAG_DOC_SCORE_THRESHOLD")
    rag_doc_full_fetch_max_chunks: int = Field(
        default=20, alias="RAG_DOC_FULL_FETCH_MAX_CHUNKS"
    )
    rag_lexical_mode: Literal["legacy", "bm25"] = Field(
        default="bm25", alias="RAG_LEXICAL_MODE"
    )
    rag_fusion_mode: Literal["legacy", "rrf"] = Field(
        default="rrf", alias="RAG_FUSION_MODE"
    )
    rag_reranker_enabled: bool = Field(default=False, alias="RAG_RERANKER_ENABLED")
    rag_reranker_model: str = Field(
        default="BAAI/bge-reranker-base", alias="RAG_RERANKER_MODEL"
    )
    rag_reranker_top_n: int = Field(default=20, alias="RAG_RERANKER_TOP_N", ge=1)
    rag_evidence_judge_enabled: bool = Field(
        default=False, alias="RAG_EVIDENCE_JUDGE_ENABLED"
    )
    rag_evidence_judge_model: str = Field(
        default="deepseek-chat", alias="RAG_EVIDENCE_JUDGE_MODEL"
    )

    # Agent
    query_planner_mode: Literal["rule_fallback", "hybrid", "llm"] = Field(
        default="hybrid", alias="QUERY_PLANNER_MODE"
    )
    query_planner_model: str = Field(
        default="deepseek-chat", alias="QUERY_PLANNER_MODEL"
    )
    rag_max_subquestions: int = Field(default=5, alias="RAG_MAX_SUBQUESTIONS", ge=1, le=5)
    rag_max_retry: int = Field(default=1, alias="RAG_MAX_RETRY", ge=0, le=1)
    enable_fallback: bool = Field(default=True, alias="ENABLE_FALLBACK")

    # 服务
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # JWT 鉴权
    jwt_secret_key: str = Field(
        default="zhku-campus-agent-change-me-in-production",
        alias="JWT_SECRET_KEY",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=60 * 24 * 7, alias="JWT_EXPIRE_MINUTES")

    @field_validator("vector_store_path", "sqlite_path", mode="before")
    @classmethod
    def _resolve_data_path(cls, value: str | Path) -> Path:
        """将 .env 中的相对路径固定解析到项目根目录。"""
        path = Path(value)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    def ensure_dirs(self) -> None:
        """创建必要的目录。"""
        for sub in ["raw", "cleaned", "metadata", "sqlite", "vector_store", "users", "uploads"]:
            (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
        self.vector_store_path.mkdir(parents=True, exist_ok=True)
        # 保留 sqlite 目录，便于从旧库迁移，不删除原文件
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
