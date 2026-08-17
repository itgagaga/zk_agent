"""用户私有智能文档上传 API。

上传的文档解析后写入 zhku_user_docs 向量集合，仅该用户可检索。
每次上传为覆盖写：替换该用户原有全部私有文档（与简历上传逻辑一致）。
原始文件落盘：data/users/{user_id}/uploads/

接口：
  POST   /api/upload               上传（需登录）
  GET    /api/upload/docs          列出当前用户文档
  DELETE /api/upload/docs/{doc_id} 删除自己的文档
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.auth.deps import get_current_user
from backend.config import settings
from backend.database.models import User, UserDocument
from backend.database.session import get_db
from backend.rag.vector_store import get_vector_store
from backend.storage.user_files import (
    delete_path,
    resolve_user_file,
    to_data_relative,
    user_uploads_dir,
)
from crawler.chunking import records_to_store_payload, split_document

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def _guess_title(stem: str) -> str:
    name = re.sub(r"^\d+\.", "", stem)
    return name.strip() or stem


def _remove_user_document(row: UserDocument, db: Session) -> None:
    """删除单条用户文档：向量 + 文件 + 元数据。"""
    store = get_vector_store()
    store.delete_documents(
        where={"doc_id": row.doc_id},
        collection="user_docs",
    )
    delete_path(resolve_user_file(row.file_path))
    db.delete(row)


def _clear_user_documents(user_id: int, db: Session) -> int:
    """清空用户全部私有文档，返回删除数量（不 commit，由调用方统一提交）。"""
    rows = db.query(UserDocument).filter(UserDocument.user_id == user_id).all()
    for row in rows:
        _remove_user_document(row, db)
    return len(rows)


@router.post("")
async def upload_file(
    file: UploadFile = File(...),
    department: str = Form("文档库"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """上传文件到当前用户的私有知识库（覆盖写：替换原有全部文档）。"""
    filename = file.filename or "unknown"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {suffix}，仅支持 {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件超过 20MB 限制")
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")

    doc_id = f"ud_{uuid.uuid4().hex[:12]}"
    uploads = user_uploads_dir(current_user.id)
    raw_path = uploads / f"{doc_id}{suffix}"
    raw_path.write_bytes(content)

    try:
        parsed = parse_file(raw_path)
    except Exception as e:
        delete_path(raw_path)
        raise HTTPException(status_code=422, detail=f"文件解析失败: {e}") from e

    text = parsed.get("full_text", "").strip()
    if not text:
        delete_path(raw_path)
        raise HTTPException(status_code=422, detail="文件解析后文本为空，可能是扫描版 PDF")

    title = _guess_title(Path(filename).stem)
    department = department.strip() or "文档库"

    records = split_document(
        text,
        doc_title=title,
        department=department,
        short_doc_max=settings.short_doc_max_size,
        parent_max_size=settings.parent_max_size,
        child_target_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        min_chunk_size=settings.chunk_min_size,
    )
    if not records:
        delete_path(raw_path)
        raise HTTPException(status_code=422, detail="文件切分后无有效内容")

    replaced_count = _clear_user_documents(current_user.id, db)

    store = get_vector_store()
    ids, chunk_texts, metadatas = records_to_store_payload(
        records,
        doc_id,
        {
            "title": title,
            "department": department,
            "source_url": "",
            "doc_id": doc_id,
            "filename": filename,
            "user_id": int(current_user.id),
        },
    )
    store.add_documents(ids=ids, texts=chunk_texts, metadatas=metadatas, collection="user_docs")

    rel = to_data_relative(raw_path)
    row = UserDocument(
        user_id=current_user.id,
        doc_id=doc_id,
        title=title,
        filename=filename,
        file_path=rel,
        department=department,
        file_type=suffix.lstrip("."),
        size=len(content),
        page_count=int(parsed.get("page_count") or 0),
        chunk_count=len(records),
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "doc_id": doc_id,
            "filename": filename,
            "title": title,
            "department": department,
            "chunk_count": len(records),
            "page_count": parsed.get("page_count", 0),
            "replaced_count": replaced_count,
            "message": (
                f"已用 {filename} 覆盖你的私有知识库"
                if replaced_count
                else f"已将 {filename} 写入你的私有知识库"
            ),
        },
    )


@router.get("/docs")
async def list_docs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """列出当前用户的私有文档。"""
    rows = (
        db.query(UserDocument)
        .filter(UserDocument.user_id == current_user.id)
        .order_by(UserDocument.created_at.desc())
        .all()
    )
    docs = [
        {
            "doc_id": r.doc_id,
            "filename": r.filename,
            "title": r.title,
            "department": r.department,
            "size": r.size,
            "page_count": r.page_count,
            "chunk_count": r.chunk_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return {"docs": docs, "count": len(docs)}


@router.delete("/docs/{doc_id}")
async def delete_doc(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """删除当前用户的文档：向量 + 文件 + 元数据。"""
    row = (
        db.query(UserDocument)
        .filter(UserDocument.doc_id == doc_id, UserDocument.user_id == current_user.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    _remove_user_document(row, db)
    db.commit()
    return {"ok": True, "doc_id": doc_id, "message": "已删除"}
