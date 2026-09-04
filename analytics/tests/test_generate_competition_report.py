import json
import tempfile
import unittest
from pathlib import Path

from analytics.generate_competition_report import build_analysis, write_outputs


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = (
    PROJECT_ROOT / "analytics" / "results" / "paper_metrics_2026-07-29.json"
)


class GenerateCompetitionReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    def test_snapshot_analysis_matches_frozen_evidence(self):
        analysis = build_analysis(self.snapshot)

        self.assertAlmostEqual(analysis["routing"]["accuracy"], 26 / 27)
        self.assertAlmostEqual(analysis["routing"]["cohen_kappa"], 0.9583333)
        self.assertEqual(analysis["rag"]["dominated_k"], [10])
        self.assertTrue(analysis["top_k_optimization"]["empirically_dominated"])
        self.assertEqual(len(analysis["provenance"]["source_digest_sha256"]), 64)

    def test_write_outputs_creates_machine_and_human_readable_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            outputs = write_outputs(
                self.snapshot,
                SNAPSHOT_PATH,
                Path(directory),
                charts=False,
            )

            self.assertEqual(len(outputs), 2)
            self.assertTrue(all(path.exists() for path in outputs))
            metrics = json.loads((Path(directory) / "competition_metrics.json").read_text(encoding="utf-8"))
            report = (Path(directory) / "competition_report.md").read_text(encoding="utf-8")
            self.assertIn("multiclass_mcc", metrics["routing"])
            self.assertIn("Mann–Whitney", report)
            self.assertIn("解释边界", report)


if __name__ == "__main__":
    unittest.main()

