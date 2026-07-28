"""分析模块的数据读取函数。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def load_chroma_records(database_path: Path) -> list[dict[str, Any]]:
    """以只读方式从 Chroma SQLite 读取文档、标题与 metadata。"""
    resolved = Path(database_path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Chroma 数据库不存在：{resolved}")

    connection = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    query = """
        SELECT
            c.name AS collection,
            e.embedding_id AS chunk_id,
            MAX(CASE WHEN m.key = 'title' THEN m.string_value END) AS title,
            MAX(CASE WHEN m.key = 'department' THEN m.string_value END) AS department,
            MAX(CASE WHEN m.key = 'source_url' THEN m.string_value END) AS source_url,
            MAX(CASE WHEN m.key = 'publish_date' THEN m.string_value END) AS publish_date,
            MAX(CASE WHEN m.key = 'sub_dir' THEN m.string_value END) AS sub_dir,
            MAX(CASE WHEN m.key = 'doc_id' THEN m.string_value END) AS doc_id,
            MAX(CASE WHEN m.key = 'user_id' THEN m.int_value END) AS user_id,
            MAX(CASE WHEN m.key = 'chroma:document' THEN m.string_value END) AS document
        FROM collections c
        JOIN segments s ON s.collection = c.id
        JOIN embeddings e ON e.segment_id = s.id
        LEFT JOIN embedding_metadata m ON m.id = e.id
        GROUP BY c.name, e.id, e.embedding_id
        ORDER BY c.name, e.embedding_id
    """
    try:
        rows = connection.execute(query).fetchall()
    finally:
        connection.close()

    records: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        record["title"] = record.get("title") or "未命名文档"
        record["department"] = record.get("department") or "未标注"
        record["document"] = record.get("document") or ""
        records.append(record)
    return records
