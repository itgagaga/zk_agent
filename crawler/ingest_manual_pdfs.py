"""手动 PDF 摄取助手。

仲恺教务部对培养方案等附件下载启用验证码拦截，自动脚本无法直接获取 PDF。
本脚本用于将用户在浏览器中手动下载的 PDF 批量解析入库：

用法：
  1. 在浏览器打开 https://jwc.zhku.edu.cn/info/1991/28582.htm
  2. 逐一点击附件链接，输入验证码后下载 PDF
  3. 把下载好的 PDF 放到 data/manual_pdfs/ 目录（可建子目录按来源分组）
  4. 运行：python -m crawler.ingest_manual_pdfs
  5. 脚本会自动解析 PDF、写入 cleaned/metadata、增量更新向量库

支持嵌套目录：data/manual_pdfs/jwc/xxx.pdf 会归入教务部。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.rag.vector_store import get_vector_store
from crawler.common import save_cleaned, save_metadata, save_raw
from crawler.chunking import records_to_store_payload, split_document
from crawler.parse_documents import parse_pdf

# 手动 PDF 投放目录
MANUAL_PDF_DIR = settings.vector_store_path.parent / "manual_pdfs"

# 子目录 → (subdir_key, department, source_url) 映射
# subdir_key 用于 data/cleaned 与 data/metadata 的子目录命名
_SUBDIR_MAP: dict[str, tuple[str, str, str]] = {
    "jwc": ("jwc", "教务部", "https://jwc.zhku.edu.cn/"),
    "zsb": ("zsb", "招生办公室", "https://zsb.zhku.edu.cn/"),
    "yjs": ("yjs", "研究生处", "https://yjs.zhku.edu.cn/"),
    "job": ("job", "就业指导中心", "https://job.zhku.edu.cn/"),
}


def _resolve_target(pdf_path: Path) -> tuple[str, str, str]:
    """根据 PDF 所在子目录决定写入的 cleaned 子目录、部门、来源 URL。

    若在 data/manual_pdfs/ 根目录下，默认归入 jwc（培养方案最常见来源）。
    """
    rel = pdf_path.relative_to(MANUAL_PDF_DIR)
    parts = rel.parts
    if len(parts) > 1:
        top = parts[0].lower()
        if top in _SUBDIR_MAP:
            return _SUBDIR_MAP[top]
    return ("jwc", "教务部", "https://jwc.zhku.edu.cn/")


def _guess_title(stem: str) -> str:
    """从文件名猜测标题。"""
    # 去掉常见前缀如 "1." "29." 等序号
    name = re.sub(r"^\d+\.", "", stem)
    name = re.sub(r"_+$", "", name).strip()
    return name or stem


def ingest_one(pdf_path: Path, store: Any) -> int:
    """解析单个 PDF 并写入 cleaned/metadata/向量库。返回写入的 chunk 数。"""
    subdir_key, department, source_url = _resolve_target(pdf_path)
    stem = pdf_path.stem
    title = _guess_title(stem)

    print(f"  解析: {pdf_path.name} ...", end=" ", flush=True)

    try:
        parsed = parse_pdf(pdf_path)
    except Exception as e:
        print(f"❌ 解析失败: {e}")
        return 0

    text = parsed.get("full_text", "").strip()
    if not text:
        print("⚠️ 文本为空，跳过")
        return 0

    # 加结构化头部
    header_lines = [
        f"文档标题：{title}",
        f"来源部门：{department}",
        f"来源网址：{source_url}",
        f"页数：{parsed.get('page_count', 0)}",
        "",
    ]
    full_text = "\n".join(header_lines) + text

    # 保存原始 PDF 副本（统一放到 data/raw/<subdir>/）
    save_raw(subdir_key, pdf_path.name, pdf_path.read_bytes())

    # 保存清洗后文本
    cleaned_name = f"manual_{stem}.txt"
    save_cleaned(subdir_key, cleaned_name, full_text)

    # 保存元数据
    save_metadata(
        subdir_key,
        cleaned_name.replace(".txt", ".json"),
        {
            "url": source_url,
            "source_url": source_url,
            "title": title,
            "department": department,
            "page_count": parsed.get("page_count", 0),
            "ingest_source": "manual",
            "original_filename": pdf_path.name,
        },
    )

    # 增量写入向量库
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
        print("⚠️ 切分为 0 chunk，跳过")
        return 0

    id_prefix = f"{subdir_key}_manual_{stem}"
    ids, chunk_texts, metadatas = records_to_store_payload(
        records,
        id_prefix,
        {
            "title": title,
            "department": department,
            "source_url": source_url,
            "publish_date": "",
            "sub_dir": subdir_key,
        },
    )
    store.add_documents(ids=ids, texts=chunk_texts, metadatas=metadatas, collection="zhku")

    print(f"OK ({parsed.get('page_count', 0)} 页, {len(records)} chunks)")
    return len(records)


def main() -> None:
    """主入口：扫描 data/manual_pdfs/ 并摄取全部 PDF。"""
    if not MANUAL_PDF_DIR.exists():
        MANUAL_PDF_DIR.mkdir(parents=True, exist_ok=True)
        print(f"已创建投放目录：{MANUAL_PDF_DIR}")
        print("请把手动下载的 PDF 放入该目录（可建 jwc/zsb 等子目录按来源分组），")
        print("然后重新运行：python -m crawler.ingest_manual_pdfs")
        return

    pdfs = sorted(MANUAL_PDF_DIR.rglob("*.pdf"))
    if not pdfs:
        print(f"未在 {MANUAL_PDF_DIR} 下找到任何 PDF")
        print("请先把手动下载的 PDF 放入该目录，再重新运行。")
        return

    print("=" * 60)
    print(f"手动 PDF 摄取：共发现 {len(pdfs)} 份 PDF")
    print("=" * 60)

    store = get_vector_store()
    total_chunks = 0
    for pdf in pdfs:
        total_chunks += ingest_one(pdf, store)

    print("-" * 60)
    print(f"摄取完成：共写入 {total_chunks} chunks 到向量库")
    print("向量库已增量更新，无需重新运行 build_kb")


if __name__ == "__main__":
    main()
