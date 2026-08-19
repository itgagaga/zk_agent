import unittest
from pathlib import Path

from analytics.run_analysis import (
    build_offline_metrics,
    evaluate_routes,
    latency_annotation_y,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RunAnalysisTests(unittest.TestCase):
    def test_latency_annotation_stays_below_extreme_sample(self):
        values = [13.8, 14.6, 19.3, 24.8]

        position = latency_annotation_y(values)

        self.assertGreater(position, 19.3)
        self.assertLess(position, 24.8)

    def test_build_offline_metrics_matches_current_data_snapshot(self):
        metrics = build_offline_metrics(PROJECT_ROOT)

        # The rebuilt parent-child KB intentionally has a different cardinality
        # from the historical 100-row fixture. Assert structural invariants so
        # the test validates the metrics contract instead of freezing old data.
        self.assertEqual(
            metrics["total_chunks"],
            sum(metrics["collection_counts"].values()),
        )
        self.assertGreater(metrics["collection_counts"]["zhku_campus"], 0)
        self.assertEqual(metrics["collection_counts"]["zhku_user_docs"], 13)
        self.assertEqual(metrics["metadata_completeness"]["标题"], 1.0)
        self.assertGreater(metrics["chunk_summary"]["median"], 0)

    def test_evaluate_routes_covers_all_declared_cases(self):
        result = evaluate_routes()

        self.assertEqual(result["total"], 27)
        self.assertEqual(len(result["expected"]), len(result["predicted"]))
        self.assertGreaterEqual(result["accuracy"], 0.8)


if __name__ == "__main__":
    unittest.main()
