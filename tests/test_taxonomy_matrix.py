import csv
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "01 Reports"
MATRIX = ROOT / "02 Evidence" / "regression-coverage-matrix.csv"


class TaxonomyMatrixTests(unittest.TestCase):
    def rows(self):
        with MATRIX.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertTrue(rows)
        self.assertEqual(
            set(rows[0]),
            {
                "case_id",
                "incident_report",
                "fixture",
                "category",
                "status",
                "failure_control",
                "positive_control",
                "observable_evidence",
            },
        )
        return rows

    def test_every_current_report_is_mapped_without_transcript_copy(self):
        rows = self.rows()
        mapped = {row["incident_report"] for row in rows}
        reports = {f"01 Reports/{path.name}" for path in REPORTS.iterdir() if path.suffix in {".md", ".txt"}}
        self.assertEqual(mapped, reports)
        self.assertTrue(all("90 Raw Transcripts" not in row["observable_evidence"] for row in rows))

    def test_covered_rows_have_a_fixture_and_positive_control(self):
        for row in self.rows():
            fixture = ROOT.joinpath(*row["fixture"].split("/"))
            self.assertTrue(fixture.is_file(), row)
            if row["status"] == "COVERED":
                self.assertNotEqual(row["positive_control"], "NONE", row)
                self.assertNotIn("DRAFT", fixture.name, row)
            else:
                self.assertEqual(row["status"], "OBSERVED_NOT_REPLAY_READY", row)
                self.assertEqual(row["positive_control"], "NONE", row)

    def test_matrix_has_distinct_categories_and_expected_gaps(self):
        rows = self.rows()
        categories = {row["category"] for row in rows}
        self.assertGreaterEqual(len(categories), 8)
        self.assertIn("task_substitution", categories)
        self.assertIn("wrong_route_persistence", categories)
        self.assertTrue(any(row["status"] == "OBSERVED_NOT_REPLAY_READY" for row in rows))


if __name__ == "__main__":
    unittest.main()
