"""RAG 文档切分：结构优先 + Parent-Child + 递归兜底。

策略：
1. 短文档（<= short_doc_max）整段入库，不切分
2. 按 Markdown 标题 / 中文章节号 / 段落拆成 Parent 块
3. Parent 超长时在内部递归切 Child；检索命中 Child 后可扩展为完整 Parent
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# 章节标题行（整行匹配）
_SECTION_LINE = re.compile(
    r"^(?:"
    r"\s{0,3}#{1,6}\s+.+|"  # Markdown 标题
    r"[一二三四五六七八九十百]+[、．.]\s*.+|"  # 一、二、三、
    r"（[一二三四五六七八九十]+）\s*.+|"  # （一）（二）
    r"\d+[\.．、]\s+[\u4e00-\u9fff].+"  # 1. 报考条件
    r")$"
)

# 默认分隔符优先级：段落 → 换行 → 中文句末 → 空格 → 硬切
_DEFAULT_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", " ", ""]


@dataclass
class ChunkRecord:
    """单个入库片段。"""

    text: str
    section_title: str = ""
    section_path: str = ""
    parent_id: str = ""
    chunk_role: str = "parent"  # parent | child
    chunk_index: int = 0
    embed_text: str = ""

    def __post_init__(self) -> None:
        if not self.embed_text:
            self.embed_text = self.text


def normalize_text(text: str) -> str:
    """轻量清洗：去 front matter、折叠空行，保留章节结构。"""
    text = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.DOTALL)
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if re.match(r"^\s*\|?[\s\-:|]+\|?\s*$", line) and "-" in line:
            continue
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"__([^_]+)__", r"\1", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _section_title_from_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
    return line.strip()


def split_into_sections(text: str) -> list[tuple[str, str]]:
    """按章节标题切分为 (section_title, section_body) 列表。"""
    lines = text.splitlines()
    sections: list[tuple[str, str]] = []
    current_title = ""
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_body
        body = "\n".join(current_body).strip()
        if current_title or body:
            sections.append((current_title, body))
        current_title = ""
        current_body = []

    for line in lines:
        if _SECTION_LINE.match(line.strip()):
            flush()
            current_title = _section_title_from_line(line)
        else:
            current_body.append(line)

    flush()
    return sections


def split_by_paragraphs(text: str) -> list[tuple[str, str]]:
    """无章节标题时按空行分段。"""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not parts:
        return [("", text.strip())] if text.strip() else []
    if len(parts) == 1:
        return [("", parts[0])]
    return [(f"第{i + 1}段", p) for i, p in enumerate(parts)]


def recursive_split(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    min_chunk_size: int,
    separators: list[str] | None = None,
) -> list[str]:
    """在 Parent 内部按分隔符递归切分 Child。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    seps = separators or _DEFAULT_SEPARATORS
    chunks: list[str] = []

    def _split_remaining(remaining: str, sep_idx: int) -> list[str]:
        remaining = remaining.strip()
        if not remaining:
            return []
        if len(remaining) <= chunk_size:
            return [remaining]

        if sep_idx >= len(seps):
            # 硬切兜底
            result: list[str] = []
            start = 0
            while start < len(remaining):
                end = min(start + chunk_size, len(remaining))
                piece = remaining[start:end].strip()
                if piece:
                    result.append(piece)
                if end >= len(remaining):
                    break
                start = max(end - chunk_overlap, start + 1)
            return result

        sep = seps[sep_idx]
        if sep == "":
            return _split_remaining(remaining, sep_idx + 1)

        if sep not in remaining:
            return _split_remaining(remaining, sep_idx + 1)

        parts = remaining.split(sep)
        merged: list[str] = []
        buf = ""
        for i, part in enumerate(parts):
            piece = part if i == len(parts) - 1 else part + sep
            candidate = (buf + piece) if buf else piece
            if len(candidate) <= chunk_size:
                buf = candidate
            else:
                if buf.strip():
                    merged.append(buf.strip())
                if len(piece) > chunk_size:
                    merged.extend(_split_remaining(piece.strip(), sep_idx + 1))
                    buf = ""
                else:
                    buf = piece
        if buf.strip():
            merged.append(buf.strip())

        # 合并过短片段
        if min_chunk_size > 0 and len(merged) > 1:
            combined: list[str] = []
            for piece in merged:
                if combined and len(piece) < min_chunk_size:
                    combined[-1] = (combined[-1] + "\n" + piece).strip()
                else:
                    combined.append(piece)
            merged = combined

        return merged

    chunks = _split_remaining(text, 0)

    # overlap：相邻 child 之间保留少量重复上下文
    if chunk_overlap > 0 and len(chunks) > 1:
        overlapped: list[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            cur = chunks[i]
            tail = prev[-chunk_overlap:] if len(prev) > chunk_overlap else prev
            overlapped.append((tail + cur).strip())
        chunks = overlapped

    return [c for c in chunks if c and len(c) >= max(min_chunk_size // 2, 1)]


def build_embed_text(
    text: str,
    *,
    doc_title: str = "",
    section_title: str = "",
    department: str = "",
) -> str:
    """为 embedding 添加文档/章节上下文前缀。"""
    parts = [p for p in (doc_title, section_title, department) if p]
    if parts:
        return f"【{' · '.join(parts)}】\n{text}"
    return text


def split_document(
    text: str,
    *,
    doc_title: str = "",
    department: str = "",
    short_doc_max: int = 800,
    parent_max_size: int = 1500,
    child_target_size: int = 600,
    chunk_overlap: int = 80,
    min_chunk_size: int = 80,
) -> list[ChunkRecord]:
    """结构感知切分，返回 Parent/Child 片段列表。"""
    text = normalize_text(text)
    if not text:
        return []

    if len(text) <= short_doc_max:
        embed = build_embed_text(
            text, doc_title=doc_title, department=department
        )
        return [
            ChunkRecord(
                text=text,
                embed_text=embed,
                parent_id="p0",
                chunk_role="parent",
                chunk_index=0,
            )
        ]

    sections = split_into_sections(text)
    # 若只识别出一个无标题大块，改按段落切
    if len(sections) <= 1 and len(text) > short_doc_max:
        sections = split_by_paragraphs(text)

    records: list[ChunkRecord] = []
    for sec_idx, (section_title, section_body) in enumerate(sections):
        if section_title and section_body:
            section_text = f"{section_title}\n{section_body}"
        elif section_title:
            section_text = section_title
        else:
            section_text = section_body

        section_text = section_text.strip()
        if not section_text:
            continue

        parent_id = f"p{sec_idx}"
        section_path = section_title or f"第{sec_idx + 1}节"

        if len(section_text) <= parent_max_size:
            embed = build_embed_text(
                section_text,
                doc_title=doc_title,
                section_title=section_title,
                department=department,
            )
            records.append(
                ChunkRecord(
                    text=section_text,
                    embed_text=embed,
                    section_title=section_title,
                    section_path=section_path,
                    parent_id=parent_id,
                    chunk_role="parent",
                    chunk_index=sec_idx,
                )
            )
            continue

        children = recursive_split(
            section_text,
            chunk_size=child_target_size,
            chunk_overlap=chunk_overlap,
            min_chunk_size=min_chunk_size,
        )
        for child_idx, child_text in enumerate(children):
            embed = build_embed_text(
                child_text,
                doc_title=doc_title,
                section_title=section_title,
                department=department,
            )
            records.append(
                ChunkRecord(
                    text=child_text,
                    embed_text=embed,
                    section_title=section_title,
                    section_path=section_path,
                    parent_id=parent_id,
                    chunk_role="child",
                    chunk_index=child_idx,
                )
            )

    return records


def split_into_chunks(
    text: str,
    chunk_size: int = 600,
    chunk_overlap: int = 80,
    *,
    doc_title: str = "",
    department: str = "",
    parent_max_size: int = 1500,
    short_doc_max: int = 800,
    min_chunk_size: int = 80,
) -> list[str]:
    """向后兼容：返回 embed 文本列表。"""
    records = split_document(
        text,
        doc_title=doc_title,
        department=department,
        short_doc_max=short_doc_max,
        parent_max_size=parent_max_size,
        child_target_size=chunk_size,
        chunk_overlap=chunk_overlap,
        min_chunk_size=min_chunk_size,
    )
    return [r.embed_text for r in records]


def records_to_store_payload(
    records: list[ChunkRecord],
    id_prefix: str,
    base_metadata: dict[str, Any],
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """将 ChunkRecord 列表转为向量库写入格式 (ids, texts, metadatas)。"""
    ids: list[str] = []
    texts: list[str] = []
    metadatas: list[dict[str, Any]] = []
    for i, rec in enumerate(records):
        ids.append(f"{id_prefix}_{i}")
        texts.append(rec.embed_text)
        scoped_parent = f"{id_prefix}_{rec.parent_id}" if rec.parent_id else ""
        meta = {
            **base_metadata,
            "section_title": rec.section_title or "",
            "section_path": rec.section_path or "",
            "parent_id": scoped_parent,
            "chunk_role": rec.chunk_role,
            "chunk_index": int(rec.chunk_index),
            "doc_key": id_prefix,
        }
        metadatas.append(meta)
    return ids, texts, metadatas
