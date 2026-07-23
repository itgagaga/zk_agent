"""永久知识库文档上传 API。

上传的文档解析后写入 zhku_documents 向量集合，成为永久共享知识库的一部分。
所有用户的提问都会经由 RAG 相似度检索自动判断是否命中这些文档——
相关问题才会检索到，无关问题不会干扰。

接口：
  POST   /api/upload               上传文件到永久知识库（multipart/form-data）
  GET    /api/upload/docs          列出已上传的永久文档
  DELETE /api/upload/docs/{doc_id} 删除指定文档
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.rag.vector_store import get_vector_store
from crawler.parse_documents import parse_file, split_into_chunks

router = APIRouter()

# 上传文件存储目录
UPLOAD_DIR = settings.vector_store_path.parent / "uploads"
# 全局文档清单
MANIFEST_PATH = UPLOAD_DIR / "manifest.json"
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def _ensure_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _load_manifest() -> list[dict[str, Any]]:
    """加载全局文档清单。"""
    if not MANIFEST_PATH.exists():
        return []
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_manifest(docs: list[dict[str, Any]]) -> None:
    _ensure_dir()
    MANIFEST_PATH.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")


def _guess_title(stem: str) -> str:
    """从文件名猜测标题。"""
    name = re.sub(r"^\d+\.", "", stem)
    return name.strip() or stem


@router.post("")
async def upload_file(
    file: UploadFile = File(...),
    department: str = Form("文档库"),
) -> JSONResponse:
    """上传文件到永久知识库。

    - 接收文件 + 可选 department（来源标签）
    - 保存原始文件到 data/uploads/
    - 解析文本 → 切分 → 向量化 → 写入 zhku_documents（永久共享）
    - 更新全局 manifest.json
    """
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

    _ensure_dir()
    doc_id = f"kb_{uuid.uuid4().hex[:12]}"
    raw_path = UPLOAD_DIR / f"{doc_id}{suffix}"
    raw_path.write_bytes(content)

    # 解析文件
    try:
        parsed = parse_file(raw_path)
    except Exception as e:
        raw_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"文件解析失败: {e}")

    text = parsed.get("full_text", "").strip()
    if not text:
        raw_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="文件解析后文本为空，可能是扫描版 PDF")

    title = _guess_title(Path(filename).stem)
    department = department.strip() or "文档库"

    # 切分 + 向量化
    chunks = split_into_chunks(
        text,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    if not chunks:
        raw_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="文件切分后无有效内容")

    store = get_vector_store()
    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "title": title,
            "department": department,
            "source_url": "",
            "doc_id": doc_id,
            "filename": filename,
        }
        for _ in chunks
    ]
    store.add_documents(ids=ids, texts=chunks, metadatas=metadatas, collection="document")

    # 更新 manifest
    docs = _load_manifest()
    doc_info = {
        "doc_id": doc_id,
        "filename": filename,
        "title": title,
        "department": department,
        "size": len(content),
        "page_count": parsed.get("page_count", 0),
        "chunk_count": len(chunks),
    }
    docs.append(doc_info)
    _save_manifest(docs)

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "doc_id": doc_id,
            "filename": filename,
            "title": title,
            "department": department,
            "chunk_count": len(chunks),
            "page_count": parsed.get("page_count", 0),
            "message": f"已将 {filename} 加入永久知识库",
        },
    )


@router.get("/docs")
async def list_docs() -> dict:
    """列出永久知识库中的全部文档。"""
    docs = _load_manifest()
    return {"docs": docs, "count": len(docs)}


@router.delete("/docs/{doc_id}")
async def delete_doc(doc_id: str) -> dict:
    """从永久知识库删除指定文档：向量库 + 原始文件 + manifest。"""
    docs = _load_manifest()
    target = next((d for d in docs if d["doc_id"] == doc_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 从向量库删除
    store = get_vector_store()
    store.delete_documents(where={"doc_id": doc_id}, collection="document")

    # 删除原始文件
    for f in UPLOAD_DIR.iterdir():
        if f.name.startswith(doc_id):
            f.unlink(missing_ok=True)

    # 更新 manifest
    docs = [d for d in docs if d["doc_id"] != doc_id]
    _save_manifest(docs)

    return {"ok": True, "doc_id": doc_id, "message": "已删除"}
