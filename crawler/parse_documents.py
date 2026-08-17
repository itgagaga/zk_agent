"""文档解析模块。

解析 PDF / DOC / DOCX / HTML 长文，提取章节、正文、表格、页码，
为智能文档 RAG 提供素材。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def parse_pdf(file_path: str | Path) -> dict[str, Any]:
    """解析 PDF 文件，返回文本和章节信息。

    使用 pymupdf（fitz）。若提取文本为空（扫描版 PDF），自动降级用 OCR。
    """
    import fitz  # type: ignore[import-not-found]

    doc = fitz.open(str(file_path))
    pages: list[dict[str, Any]] = []
    full_text_parts: list[str] = []

    for page_idx, page in enumerate(doc):
        text = page.get_text("text")
        pages.append({"page_number": page_idx + 1, "text": text})
        full_text_parts.append(text)

    full_text = "\n".join(full_text_parts)

    # 扫描版 PDF 降级：pymupdf 提取为空时使用 OCR
    if not full_text.strip():
        full_text = _ocr_pdf(doc)
        # 同步更新 pages 信息
        if full_text.strip():
            # OCR 结果按页重新分配（简化处理：全部放在第 1 页）
            pages = [{"page_number": 1, "text": full_text}]

    return {
        "file_path": str(file_path),
        "page_count": len(pages) if pages else doc.page_count,
        "pages": pages,
        "full_text": full_text,
    }


def _ocr_pdf(doc: Any) -> str:
    """对扫描版 PDF 使用 RapidOCR 提取文字。

    逐页渲染为图片后 OCR，返回全部文本。
    """
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]
    except ImportError:
        print("[OCR] rapidocr-onnxruntime 未安装，跳过 OCR")
        return ""

    ocr = RapidOCR()
    all_text: list[str] = []

    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        result, _ = ocr(img_bytes)
        if result:
            for line in result:
                # result 每项: ([坐标], text, confidence)
                all_text.append(line[1])

    return "\n".join(all_text)


def parse_docx(file_path: str | Path) -> dict[str, Any]:
    """解析 DOCX 文件。"""
    from docx import Document  # type: ignore[import-not-found]

    doc = Document(str(file_path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    full_text = "\n".join(paragraphs)
    return {
        "file_path": str(file_path),
        "paragraphs": paragraphs,
        "full_text": full_text,
    }


def parse_doc(file_path: str | Path) -> dict[str, Any]:
    """解析旧版 DOC 文件。

    DOC 格式支持有限，建议优先转换为 DOCX。
    """
    # TODO: 接入 antiword / libreoffice 转换
    return {"file_path": str(file_path), "full_text": "", "note": "DOC 暂未实现解析"}


def parse_html_long(html: str) -> dict[str, Any]:
    """解析 HTML 长文（如通知公告、章程页面）。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "iframe"]):
        tag.decompose()
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    text = soup.get_text(separator="\n", strip=True)
    return {"title": title, "full_text": text}


def parse_file(file_path: str | Path) -> dict[str, Any]:
    """根据扩展名自动选择解析器。"""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix == ".docx":
        return parse_docx(path)
    if suffix == ".doc":
        return parse_doc(path)
    if suffix in (".html", ".htm"):
        return parse_html_long(path.read_text(encoding="utf-8", errors="ignore"))
    if suffix in (".txt", ".md"):
        return {"file_path": str(path), "full_text": path.read_text(encoding="utf-8")}
    raise ValueError(f"不支持的文件格式: {suffix}")


def split_into_chunks(
    text: str,
    chunk_size: int = 600,
    chunk_overlap: int = 80,
    **kwargs: Any,
) -> list[str]:
    """结构感知切分（兼容旧接口，返回 embed 文本列表）。"""
    from crawler.chunking import split_into_chunks as _split

    return _split(
        text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        **kwargs,
    )


def split_document(text: str, **kwargs: Any) -> list[Any]:
    """结构感知切分，返回 ChunkRecord 列表。"""
    from crawler.chunking import split_document as _split_document

    return _split_document(text, **kwargs)
