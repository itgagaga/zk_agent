from pathlib import Path

import fitz

from backend.rag import pdf_context
from crawler.parse_documents import parse_pdf, _pdf_table_markdown


def _write_course_pdf(path: Path, course="Databases"):
    """A ruled table with deliberate empty semester cells, like a curriculum PDF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open() as doc:
        page = doc.new_page(width=700, height=400)
        xs = [30, 190, 235, 280, 325, 370, 415, 460, 505, 550, 595]
        ys = [60, 95, 130, 165]
        for x in xs:
            page.draw_line((x, ys[0]), (x, ys[-1]))
        for y in ys:
            page.draw_line((xs[0], y), (xs[-1], y))
        rows = [
            ["Course", "Credit", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"],
            [course, "4.5", "", "", "", "", "72", "", "", ""],
            ["Software", "3", "", "", "", "", "", "48", "", ""],
        ]
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                if value:
                    page.insert_text((xs[column_index] + 4, ys[row_index] + 20), value, fontsize=10)
        page.insert_text((30, 35), "Curriculum: required credits 157", fontsize=10)
        doc.save(path)


def test_pdf_context_keeps_empty_semester_columns_and_text_once(tmp_path):
    path = tmp_path / "curriculum.pdf"
    _write_course_pdf(path)

    parsed = parse_pdf(path, preserve_tables=True)

    assert parsed["has_tables"] is True
    assert "required credits 157" in parsed["full_text"]
    assert "| Databases | 4.5 |  |  |  |  | 72 |  |  |  |" in parsed["full_text"]
    assert "| Software | 3 |  |  |  |  |  | 48 |  |  |" in parsed["full_text"]
    assert parsed["full_text"].count("Databases") == 1


def test_multirow_chinese_semester_headers_explicitly_map_course_to_term():
    rows = [
        ["课程类别", "课程名称", "学时", "学分", "开课学期", None, None, None, None, None, None, None],
        [None, None, None, None, "一", "二", "三", "四", "五", "六", "七", "八"],
        ["专业必修", "WEB程序设计", "60", "3.5", "", "", "", "", "60", "", "", ""],
        [None, "软件体系结构与设计模式", "48", "3", "", "", "", "", "", "48", "", ""],
    ]
    text = _pdf_table_markdown(rows)
    assert "WEB程序设计（开课学期：第5学期）" in text
    assert "WEB程序设计（开课学期：第6学期）" not in text
    assert "软件体系结构与设计模式（开课学期：第6学期）" in text


def test_original_pdf_lookup_and_cache_stay_with_current_user(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_context, "user_root", lambda user_id: tmp_path / str(user_id))
    _write_course_pdf(tmp_path / "7/uploads/ud_a11.pdf", "FirstUserCourse")
    _write_course_pdf(tmp_path / "8/uploads/ud_a11.pdf", "OtherUserCourse")

    first = pdf_context.user_pdf_table_context("ud_a11", user_id=7)
    second = pdf_context.user_pdf_table_context("ud_a11", user_id=8)

    assert "FirstUserCourse" in first
    assert "OtherUserCourse" not in first
    assert "OtherUserCourse" in second
    assert pdf_context.user_pdf_table_context("../ud_a11", user_id=7) is None
    assert pdf_context.user_pdf_table_context("ud_a11", user_id=9) is None


def test_missing_or_unreadable_original_pdf_keeps_index_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_context, "user_root", lambda user_id: tmp_path / str(user_id))
    path = tmp_path / "7/uploads/ud_a11.pdf"
    path.parent.mkdir(parents=True)
    path.write_text("damaged PDF", encoding="utf-8")
    assert pdf_context.user_pdf_table_context("ud_a11", user_id=7) is None


def test_full_document_enrichment_uses_table_context_without_rewriting_index(monkeypatch):
    from backend.rag.retriever import RAGRetriever

    hit = {"chunk_id": "ud_a11_0", "title": "Curriculum", "score": 0.9,
           "dense_rank": 1, "snippet": "flattened table",
           "metadata": {"doc_id": "ud_a11", "user_id": 7}}

    class Store:
        def count_documents(self, **kwargs):
            return 1

        def get_chunks_by_doc_id(self, doc_id, **kwargs):
            return [{**hit, "score": 0.5}]

    monkeypatch.setattr("backend.rag.retriever.user_pdf_table_context",
                        lambda doc_id, *, user_id: "| Course | S5 | S6 |\n| Databases | 72 | |")
    retriever = RAGRetriever()
    retriever.store = Store()
    hits, full_doc = retriever._enrich_user_doc_hits([hit], 15, user_id=7)

    assert full_doc
    assert len(hits) == 1
    assert "| Databases | 72 | |" in hits[0]["snippet"]
    assert hits[0]["dense_rank"] == 1
    assert hits[0]["metadata"]["context_format"] == "pdf_tables"
    assert hit["snippet"] == "flattened table"
