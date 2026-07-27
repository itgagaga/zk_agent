"""将旧 SQLite（zhku.db）数据迁移到 MySQL。

运行方式：
    python -m backend.database.migrate_sqlite_to_mysql

说明：
    - 不删除、不覆盖原 SQLite 文件；
    - 按主键 id 去重：MySQL 中已存在相同 id 的行则跳过；
    - 跳过 SQLite FTS 虚拟表（*_fts）。
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from backend.config import settings
from backend.database.session import apply_schema, engine as mysql_engine

# 业务表（不含 FTS 虚拟表）
TABLES = [
    "school_profile",
    "campus",
    "organization",
    "major",
    "download_resource",
    "service_link",
    "contact",
    "news_article",
    "job_posting",
    "document",
    "document_chunk",
    "document_qa_log",
]


def _quote_ident(name: str) -> str:
    return f"`{name.replace('`', '``')}`"


def _table_columns(conn_engine: Engine, table: str) -> list[str]:
    insp = inspect(conn_engine)
    return [col["name"] for col in insp.get_columns(table)]


def migrate(sqlite_path: Path | None = None) -> dict[str, int]:
    """从 SQLite 逐表拷贝到 MySQL，返回各表插入行数。"""
    path = Path(sqlite_path or settings.sqlite_path)
    if not path.exists():
        raise FileNotFoundError(f"SQLite 文件不存在: {path}")

    apply_schema()

    sqlite_url = f"sqlite:///{path.resolve().as_posix()}"
    sqlite_engine = create_engine(sqlite_url)

    sqlite_tables = set(inspect(sqlite_engine).get_table_names())
    stats: dict[str, int] = {}

    with sqlite_engine.connect() as src, mysql_engine.begin() as dst:
        for table in TABLES:
            if table not in sqlite_tables:
                print(f"[migrate] 跳过不存在的表: {table}")
                stats[table] = 0
                continue

            src_cols = _table_columns(sqlite_engine, table)
            dst_cols = set(_table_columns(mysql_engine, table))
            cols = [c for c in src_cols if c in dst_cols]
            if not cols:
                print(f"[migrate] {table}: 无公共列，跳过")
                stats[table] = 0
                continue

            col_list = ", ".join(_quote_ident(c) for c in cols)
            rows = src.execute(text(f"SELECT {col_list} FROM {_quote_ident(table)}")).mappings().all()
            if not rows:
                print(f"[migrate] {table}: 0 行")
                stats[table] = 0
                continue

            placeholders = ", ".join(f":{c}" for c in cols)
            # 已有相同主键则跳过，避免重复插入
            insert_sql = text(
                f"INSERT IGNORE INTO {_quote_ident(table)} ({col_list}) "
                f"VALUES ({placeholders})"
            )

            inserted = 0
            for row in rows:
                result = dst.execute(insert_sql, dict(row))
                inserted += result.rowcount or 0

            # 同步自增主键，避免后续插入冲突
            if "id" in cols:
                max_id = dst.execute(
                    text(f"SELECT COALESCE(MAX(id), 0) FROM {_quote_ident(table)}")
                ).scalar()
                next_id = int(max_id) + 1
                dst.execute(text(f"ALTER TABLE {_quote_ident(table)} AUTO_INCREMENT = {next_id}"))

            stats[table] = inserted
            print(f"[migrate] {table}: 迁入 {inserted}/{len(rows)} 行")

    sqlite_engine.dispose()
    print(f"[migrate] 完成。原 SQLite 文件保留: {path}")
    return stats


def main() -> None:
    print("[migrate] SQLite → MySQL")
    migrate()


if __name__ == "__main__":
    main()
