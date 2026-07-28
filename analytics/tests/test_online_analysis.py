import tempfile
import unittest
from pathlib import Path

from analytics.run_analysis import (
    build_offline_metrics,
    evaluate_latency,
    evaluate_rag,
    evaluate_routes,
    generate_figures,
    project_vectors,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
API_BASE = "http://127.0.0.1:8000"


class OnlineAnalysisTests(unittest.TestCase):
    def test_evaluate_rag_runs_all_cases_against_live_api(self):
        result = evaluate_rag(API_BASE)

        self.assertEqual(result["total"], 20)
        self.assertEqual(sorted(result["recall_at_k"]), [1, 3, 5, 10])
        self.assertGreaterEqual(result["recall_at_k"][3], 0.5)
        self.assertEqual(
            len(result["top1_scores_correct"]) + len(result["top1_scores_incorrect"]),
            20,
        )

    def test_project_vectors_reads_all_current_embeddings(self):
        projection = project_vectors(PROJECT_ROOT)

        self.assertEqual(len(projection["x"]), 100)
        self.assertEqual(len(projection["x"]), len(projection["y"]))
        self.assertEqual(
            set(projection["collection"]),
            {"校园知识库", "用户私有文档库"},
        )

    def test_evaluate_latency_runs_one_fast_and_one_collab_query(self):
        result = evaluate_latency(
            API_BASE,
            username="zzx",
            password="123456",
            limit_per_mode=1,
        )

        self.assertEqual(result["total"], 2)
        self.assertTrue(all(item["success"] for item in result["results"]))
        self.assertEqual(
            {item["expected_mode"] for item in result["results"]},
            {"fast", "collab"},
        )

    def test_generate_figures_writes_chinese_named_png_files(self):
        offline = build_offline_metrics(PROJECT_ROOT)
        rag = evaluate_rag(API_BASE)
        routes = evaluate_routes()
        vectors = project_vectors(PROJECT_ROOT)
        with tempfile.TemporaryDirectory() as directory:
            outputs = generate_figures(
                offline=offline,
                rag=rag,
                routes=routes,
                vectors=vectors,
                latency=None,
                output_dir=Path(directory),
            )

            self.assertGreaterEqual(len(outputs), 9)
            self.assertTrue(all(path.suffix == ".png" for path in outputs))
            self.assertTrue(all(path.stat().st_size > 20_000 for path in outputs))
            self.assertTrue(any("知识库" in path.name for path in outputs))


if __name__ == "__main__":
    unittest.main()
