import unittest

from analytics.competition_statistics import (
    bootstrap_interval,
    classification_metrics,
    cliffs_delta,
    compare_latency,
    rag_metrics,
    required_sample_size_for_proportion,
    wilson_interval,
)


class CompetitionStatisticsTests(unittest.TestCase):
    def test_wilson_interval_for_perfect_small_sample_is_not_perfect_certainty(self):
        low, high = wilson_interval(8, 8)

        self.assertAlmostEqual(low, 0.6756, places=4)
        self.assertEqual(high, 1.0)

    def test_bootstrap_interval_is_reproducible(self):
        first = bootstrap_interval([1, 2, 3, 4], lambda values: sum(values) / len(values))
        second = bootstrap_interval([1, 2, 3, 4], lambda values: sum(values) / len(values))

        self.assertEqual(first, second)
        self.assertLess(first[0], 2.5)
        self.assertGreater(first[1], 2.5)

    def test_multiclass_metrics_include_agreement_beyond_chance(self):
        labels = ["A", "B", "C"]
        report = classification_metrics(
            [[3, 0, 0], [0, 2, 1], [0, 0, 3]],
            labels,
        )

        self.assertAlmostEqual(report["accuracy"], 8 / 9)
        self.assertAlmostEqual(report["micro_f1"], report["accuracy"])
        self.assertGreater(report["cohen_kappa"], 0.8)
        self.assertGreater(report["multiclass_mcc"], 0.8)
        self.assertEqual(report["per_class"][1]["recall"], 2 / 3)

    def test_rag_metrics_detect_dominated_top_k(self):
        report = rag_metrics([1, 3, 5, 10], [14, 17, 18, 18], 20)

        self.assertEqual(report["pareto_frontier_k"], [1, 3, 5])
        self.assertEqual(report["dominated_k"], [10])
        self.assertEqual(report["points"][-1]["incremental_hits"], 0)
        self.assertAlmostEqual(report["points"][2]["recall"], 0.9)

    def test_latency_comparison_reports_exact_small_sample_evidence(self):
        fast = [6.0051, 8.7835, 7.8549, 8.7583]
        collab = [12.7864, 17.7007, 10.9010, 23.3025]

        comparison = compare_latency(collab, fast)

        self.assertEqual(cliffs_delta(collab, fast), 1.0)
        self.assertEqual(comparison["mann_whitney_u"], 16.0)
        self.assertAlmostEqual(
            comparison["mann_whitney_exact_two_sided_p"], 2 / 70
        )
        self.assertGreater(comparison["median_ratio"], 1.5)

    def test_sample_size_planning_uses_conservative_proportion(self):
        self.assertEqual(required_sample_size_for_proportion(0.05), 385)
        self.assertEqual(
            required_sample_size_for_proportion(0.05, expected_proportion=0.90),
            139,
        )


if __name__ == "__main__":
    unittest.main()

