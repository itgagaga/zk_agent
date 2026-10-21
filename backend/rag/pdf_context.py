"""Read table-aware context from an already retrieved user's original PDF.

This is a read-only compatibility path for indexes made with plain-text PDF
extraction. The original file and the stored vectors remain untouched.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache

from backend.storage.user_files import user_root

logger = logging.getLogger(__name__)


@lru_cache(maxsize=8)
def _read_pdf(path: str, modified_ns: int, size: int) -> str | None:
    from crawler.parse_documents import parse_pdf

    parsed = parse_pdf(path, preserve_tables=True)
    return parsed["full_text"] if parsed.get("has_tables") else None


def user_pdf_table_context(doc_id: str, *, user_id: int) -> str | None:
    """Only open the canonical PDF within the current user's uploads directory."""
    if not re.fullmatch(r"ud_[0-9a-f]+", doc_id) or user_id <= 0:
        return None
    root = (user_root(user_id) / "uploads").resolve()
    path = (root / f"{doc_id}.pdf").resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    try:
        stat = path.stat()
        return _read_pdf(str(path), stat.st_mtime_ns, stat.st_size)
    except Exception as exc:
        # 原文件缺失、旧版 PyMuPDF 或表格识别失败时，继续使用已有检索片段。
        logger.warning("pdf_table_context_unavailable error_type=%s", type(exc).__name__)
        return None
