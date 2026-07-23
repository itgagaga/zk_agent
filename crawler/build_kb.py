"""知识库构建脚本。

将 data/cleaned/ 下的清洗文本切分、向量化，
写入 Chroma 向量库（zhku_campus / zhku_documents 两个集合）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from backend.config import settings
from backend.rag.vector_store import get_vector_store
from crawler.common import DATA_CLEANED_DIR, DATA_METADATA_DIR
from crawler.parse_documents import split_into_chunks


def build_campus_kb() -> int:
    """构建官网通用知识库（zhku_campus 集合）。

    遍历 data/cleaned/ 下所有 .txt 文件，
    按目录识别 department，切分后写入向量库。
    """
    store = get_vector_store()
    total = 0

    if not DATA_CLEANED_DIR.exists():
        print("[build_kb] data/cleaned/ 不存在，跳过")
        return 0

    for sub_dir in DATA_CLEANED_DIR.iterdir():
        if not sub_dir.is_dir():
            continue
        if sub_dir.name == "documents":
            # documents 子目录由 build_document_kb 处理
            continue
        department = _department_from_subdir(sub_dir.name)
        for text_file in _iter_text_files(sub_dir):
            text = text_file.read_text(encoding="utf-8")
            if not text.strip():
                continue
            text = _strip_markdown(text)
            if not text.strip():
                continue
            chunks = split_into_chunks(
                text,
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
            )
            if not chunks:
                continue
            meta = _load_metadata(sub_dir.name, text_file.stem)
            ids = [f"{sub_dir.name}_{text_file.stem}_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "title": meta.get("title") or text_file.stem,
                    "department": department,
                    "source_url": meta.get("source_url") or "",
                    "publish_date": meta.get("publish_date") or "",
                    "sub_dir": sub_dir.name,
                }
                for _ in chunks
            ]
            store.add_documents(
                ids=ids, texts=chunks, metadatas=metadatas, collection="zhku"
            )
            total += len(chunks)
            print(f"  - {sub_dir.name}/{text_file.name}: {len(chunks)} chunks")

    return total


def build_document_kb() -> int:
    """构建智能文档知识库（zhku_documents 集合）。

    遍历 data/cleaned/documents/ 下的文档切片，
    写入文档级向量库。
    """
    store = get_vector_store()
    total = 0

    docs_dir = DATA_CLEANED_DIR / "documents"
    if not docs_dir.exists():
        print("[build_kb] data/cleaned/documents/ 不存在，跳过")
        return 0

    for txt_file in _iter_text_files(docs_dir):
        text = txt_file.read_text(encoding="utf-8")
        if not text.strip():
            continue
        text = _strip_markdown(text)
        if not text.strip():
            continue
        chunks = split_into_chunks(
            text,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        ids = [f"doc_{txt_file.stem}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "title": txt_file.stem,
                "department": "智能文档",
                "source_url": "",
                "doc_id": txt_file.stem,
            }
            for _ in chunks
        ]
        store.add_documents(
            ids=ids, texts=chunks, metadatas=metadatas, collection="document"
        )
        total += len(chunks)

    return total


def _department_from_subdir(subdir: str) -> str:
    """根据子目录名映射部门。"""
    mapping = {
        "zhku_main": "学校主站",
        "jwc": "教务部",
        "yjs": "研究生处",
        "hqyzc": "总务后勤部",
        "wlzx": "现代教育技术中心",
        "xys": "校医院",
        "job": "就业指导中心",
        "zsb": "招生办公室",
    }
    return mapping.get(subdir, subdir)


def _iter_text_files(directory: Path) -> Iterable[Path]:
    """遍历目录下的 .txt 和 .md 文件。"""
    yield from sorted(directory.glob("*.txt"))
    yield from sorted(directory.glob("*.md"))


def _strip_markdown(text: str) -> str:
    """剥离 Markdown 的 YAML front matter 和常见标记符号，返回纯文本。

    保留标题文字、列表文字、表格单元、引用文字，方便后续切分与向量化。
    """
    # 1) 去掉 YAML front matter（--- ... ---）
    text = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.DOTALL)

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        # 2) 去掉表格分隔行（|---|---|）
        if re.match(r"^\s*\|?[\s\-:|]+\|?\s*$", line) and "-" in line:
            continue

        # 3) 去掉行首的标题井号
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)

        # 4) 去掉粗体/斜体标记 ** __ * _
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"__([^_]+)__", r"\1", line)
        line = re.sub(r"(?<!\w)\*([^*\s][^*]*)\*(?!\w)", r"\1", line)

        # 5) 链接 [text](url) -> text
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)

        # 6) 行内代码 `code` -> code
        line = re.sub(r"`([^`]+)`", r"\1", line)

        # 7) 引用前缀 > 去掉
        line = re.sub(r"^\s{0,3}>\s?", "", line)

        # 8) 列表前缀 - / * / 1. 去掉
        line = re.sub(r"^\s{0,3}[-*+]\s+", "", line)
        line = re.sub(r"^\s{0,3}\d+\.\s+", "", line)

        # 9) 表格首尾的 | 替换为空格，中间 | 替换为空格
        if line.lstrip().startswith("|"):
            line = line.replace("|", " ").strip()
            line = re.sub(r"\s+", " ", line)

        lines.append(line)

    cleaned = "\n".join(lines)
    # 折叠多余空行
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _load_metadata(subdir: str, stem: str) -> dict[str, Any]:
    """加载 metadata JSON。

    支持两种位置：
      1. data/metadata/<subdir>/<stem>.json （爬虫约定位置）
      2. data/metadata/<subdir>_<stem>.json （手工整理时的扁平位置）

    字段兼容：source_url / url / source_url_list[0]。
    """
    candidates = [
        DATA_METADATA_DIR / subdir / f"{stem}.json",
        DATA_METADATA_DIR / f"{subdir}_{stem}.json",
    ]
    for meta_file in candidates:
        if not meta_file.exists():
            continue
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        # 字段统一
        source_url = (
            data.get("source_url")
            or data.get("url")
            or ""
        )
        if not source_url:
            url_list = data.get("source_url_list") or []
            if url_list:
                source_url = url_list[0]
        data["source_url"] = source_url
        return data
    return {}


def _lookup_source_url(subdir: str, stem: str) -> str:
    """从 metadata JSON 中查找来源 URL（向后兼容）。"""
    return _load_metadata(subdir, stem).get("source_url", "")


def _lookup_publish_date(subdir: str, stem: str) -> str:
    """从 metadata JSON 中查找发布时间（向后兼容）。"""
    return _load_metadata(subdir, stem).get("publish_date", "")


def reset_collections() -> None:
    """重建前清空旧集合，避免残留过期 chunks。"""
    store = get_vector_store()
    store._init_client()
    for name in (store.collection_zhku, store.collection_doc):
        try:
            store._client.delete_collection(name)
            print(f"  - 已删除集合: {name}")
        except Exception:
            pass
    # 重置内部引用，让后续 get_or_create 重建
    store._zhku_collection = None
    store._doc_collection = None


def main() -> None:
    """主入口：构建知识库。"""
    print("[build_kb] 开始构建向量知识库 ...")
    print("[build_kb] 清空旧集合 ...")
    reset_collections()
    campus_count = build_campus_kb()
    print(f"[build_kb] 官网知识库写入 chunks: {campus_count}")
    doc_count = build_document_kb()
    print(f"[build_kb] 智能文档知识库写入 chunks: {doc_count}")
    print("[build_kb] 完成")


if __name__ == "__main__":
    main()
