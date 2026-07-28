import unittest

from analytics.core import (
    build_confusion_matrix,
    calculate_recall_at_k,
    chunk_length_summary,
    count_by_field,
    latency_summary,
)


class AnalyticsCoreTests(unittest.TestCase):
    def test_count_by_field_groups_missing_values(self):
        rows = [
            {"department": "教务部"},
            {"department": "教务部"},
            {"department": "研究生部"},
            {},
        ]

        self.assertEqual(
            count_by_field(rows, "department"),
            {"教务部": 2, "研究生部": 1, "未标注": 1},
        )

    def test_chunk_length_summary_uses_chinese_character_lengths(self):
        summary = chunk_length_summary(["仲恺校园", "RAG 检索", ""])

        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["min"], 0)
        self.assertEqual(summary["max"], 6)
        self.assertEqual(summary["median"], 4)

    def test_calculate_recall_at_k_returns_cumulative_recall(self):
        ranked_titles = [
            ["A", "B", "C"],
            ["X", "Y", "Z"],
            ["B", "A", "C"],
        ]
        expected_titles = [{"A"}, {"Z"}, {"B"}]

        self.assertEqual(
            calculate_recall_at_k(ranked_titles, expected_titles, [1, 2, 3]),
            {1: 2 / 3, 2: 2 / 3, 3: 1.0},
        )

    def test_build_confusion_matrix_preserves_label_order(self):
        labels = ["RAG", "资料下载", "天气查询"]
        matrix = build_confusion_matrix(
            expected=["RAG", "资料下载", "天气查询", "RAG"],
            predicted=["RAG", "天气查询", "天气查询", "资料下载"],
            labels=labels,
        )

        self.assertEqual(matrix, [[1, 1, 0], [0, 0, 1], [0, 0, 1]])

    def test_latency_summary_calculates_median_and_p95(self):
        summary = latency_summary([0.1, 0.2, 0.3, 0.4, 1.0])

        self.assertAlmostEqual(summary["mean"], 0.4)
        self.assertAlmostEqual(summary["median"], 0.3)
        self.assertAlmostEqual(summary["p95"], 0.88)


if __name__ == "__main__":
    unittest.main()
