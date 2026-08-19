"""RAG 切分单元测试。"""
from __future__ import annotations

import unittest

from crawler.chunking import (
    normalize_text,
    recursive_split,
    split_document,
    split_into_sections,
    records_to_store_payload,
)


class ChunkingTests(unittest.TestCase):
    def test_short_text_stays_single_chunk(self):
        text = "今天天气好。\n明天天气不好。\n学校饭好吃。"
        records = split_document(text, short_doc_max=800)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].chunk_role, "parent")

    def test_chinese_sections_split_by_structure(self):
        text = (
            "仲恺农业工程学院2026年硕士研究生招生章程\n\n"
            "一、学校概况\n"
            "学校创办于1925年。\n\n"
            "二、报考条件\n"
            "1. 中华人民共和国公民。\n"
            "2. 品德良好。\n\n"
            "三、调剂要求\n"
            "调剂考生须满足各项条件。\n"
        )
        records = split_document(
            text,
            doc_title="2026年硕士研究生招生章程",
            department="研究生处",
            short_doc_max=50,
            parent_max_size=500,
        )
        self.assertGreaterEqual(len(records), 3)
        sections = {r.section_title for r in records}
        self.assertIn("一、学校概况", sections)
        self.assertIn("二、报考条件", sections)
        self.assertIn("三、调剂要求", sections)

    def test_long_section_splits_into_children(self):
        body = "这是培养方案课程条目。" * 80
        text = f"四、课程设置\n{body}"
        records = split_document(
            text,
            parent_max_size=300,
            child_target_size=200,
            chunk_overlap=20,
            short_doc_max=100,
        )
        roles = {r.chunk_role for r in records}
        self.assertIn("child", roles)
        parent_ids = {r.parent_id for r in records}
        self.assertEqual(len(parent_ids), 1)

    def test_embed_text_has_context_prefix(self):
        records = split_document(
            "一、联系方式\n电话：020-39332025",
            doc_title="招生章程",
            department="研究生处",
            short_doc_max=50,
            parent_max_size=500,
        )
        self.assertTrue(records[0].embed_text.startswith("【"))
        self.assertIn("招生章程", records[0].embed_text)
        self.assertIn("一、联系方式", records[0].embed_text)

    def test_split_into_sections_detects_markdown(self):
        text = "# 标题A\n内容A\n\n## 标题B\n内容B"
        sections = split_into_sections(text)
        titles = [t for t, _ in sections]
        self.assertIn("标题A", titles)
        self.assertIn("标题B", titles)

    def test_recursive_split_respects_paragraphs(self):
        text = "段落一内容。\n\n段落二内容。" * 30
        parts = recursive_split(text, chunk_size=120, chunk_overlap=10, min_chunk_size=20)
        self.assertGreater(len(parts), 1)
        for part in parts:
            self.assertLessEqual(len(part), 200)

    def test_normalize_strips_front_matter(self):
        raw = "---\ntitle: x\n---\n\n正文内容"
        self.assertEqual(normalize_text(raw), "正文内容")

    def test_store_payload_has_stable_document_and_chunk_ids(self):
        records = split_document("一、联系方式\n电话：020-39332025", short_doc_max=800)
        ids, _, metadatas = records_to_store_payload(records, "jwc_contact", {"title": "联系方式"})
        self.assertEqual(ids[0], "jwc_contact_0")
        self.assertEqual(metadatas[0]["doc_id"], "jwc_contact")
        self.assertEqual(metadatas[0]["chunk_id"], "jwc_contact_0")


if __name__ == "__main__":
    unittest.main()
