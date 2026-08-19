import tempfile
import unittest
from pathlib import Path

from analytics.data_access import load_chroma_records
from analytics.evaluation import RAG_CASES, ROUTE_CASES, ROUTE_LABELS, title_matches
from analytics.plotting import format_chart_value, save_horizontal_bar_chart


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DataAccessTests(unittest.TestCase):
    def test_chart_value_formatter_supports_percentage_labels(self):
        self.assertEqual(format_chart_value(33.3333, "{:.1f}%"), "33.3%")
        self.assertEqual(format_chart_value(100, "{:.1f}%"), "100.0%")

    def test_load_chroma_records_reads_all_current_chunks(self):
        records = load_chroma_records(
            PROJECT_ROOT / "data" / "vector_store" / "chroma.sqlite3"
        )

        self.assertGreater(len(records), 100)
        self.assertEqual(
            {record["collection"] for record in records},
            {"zhku_campus", "zhku_user_docs"},
        )
        self.assertTrue(all(record["title"] for record in records))
        self.assertTrue(all(isinstance(record["document"], str) for record in records))

    def test_rag_cases_reference_titles_present_in_current_knowledge_base(self):
        records = load_chroma_records(
            PROJECT_ROOT / "data" / "vector_store" / "chroma.sqlite3"
        )
        current_titles = {record["title"] for record in records}

        self.assertGreaterEqual(len(RAG_CASES), 15)
        for case in RAG_CASES:
            self.assertTrue(
                any(title_matches(title, case.expected_titles) for title in current_titles),
                case.query,
            )

    def test_route_cases_use_declared_labels(self):
        self.assertGreaterEqual(len(ROUTE_CASES), 24)
        self.assertTrue(
            all(case.expected_label in ROUTE_LABELS for case in ROUTE_CASES)
        )

    def test_horizontal_bar_chart_writes_nonempty_png(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "chart.png"
            with self.assertNoLogs("matplotlib.font_manager", level="WARNING"):
                save_horizontal_bar_chart(
                    {"教务部": 8, "研究生处": 5},
                    title="测试图",
                    xlabel="片段数量",
                    output=output,
                )

            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 10_000)
            self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
