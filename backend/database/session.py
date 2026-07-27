"""数据库引擎与会话工厂。

业务层统一通过本模块连接 MySQL。
"""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：获取数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_database_exists() -> None:
    """若目标库不存在则创建（utf8mb4）。"""
    server_url = (
        f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}"
        f"@{settings.mysql_host}:{settings.mysql_port}/"
        f"?charset={settings.mysql_charset}"
    )
    tmp_engine = create_engine(server_url, pool_pre_ping=True)
    try:
        with tmp_engine.begin() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_database}` "
                    f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    finally:
        tmp_engine.dispose()


def apply_schema(schema_path: Path | None = None) -> None:
    """执行 schema.sql 建表。"""
    ensure_database_exists()
    path = schema_path or Path(__file__).parent / "schema.sql"
    schema_sql = path.read_text(encoding="utf-8")

    statements: list[str] = []
    buf: list[str] = []
    for line in schema_sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(buf).rstrip(";").strip())
            buf = []
    if buf:
        leftover = "\n".join(buf).strip()
        if leftover:
            statements.append(leftover)

    with engine.begin() as conn:
        for stmt in statements:
            if stmt:
                conn.execute(text(stmt))
