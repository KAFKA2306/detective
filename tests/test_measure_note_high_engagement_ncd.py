from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "measure_note_high_engagement_ncd", SCRIPTS / "measure_note_high_engagement_ncd.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class Result:
    def __init__(self, ncd: float) -> None:
        self.ncd = ncd


class NoteHighEngagementNcdTests(unittest.TestCase):
    def test_compute_pairs_counts_each_unordered_pair_once(self) -> None:
        records = [
            {"text": "a" * 1000, "normalized_prefix_sha256": "a", "year": 2022, "month": 1, "author_sha256": "x"},
            {"text": "b" * 1000, "normalized_prefix_sha256": "b", "year": 2022, "month": 2, "author_sha256": "y"},
            {"text": "c" * 1000, "normalized_prefix_sha256": "c", "year": 2026, "month": 1, "author_sha256": "z"},
        ]
        pairs = MODULE.compute_pairs(records, lambda left, right: Result(0.5))
        self.assertEqual(len(pairs), 3)
        self.assertEqual(sum(bool(row["same_author"]) for row in pairs), 0)

    def test_aggregate_reports_between_minus_within(self) -> None:
        pairs = [
            {"ncd": 0.4, "year_a": 2022, "month_a": 1, "year_b": 2022, "month_b": 2, "same_author": False},
            {"ncd": 0.8, "year_a": 2022, "month_a": 1, "year_b": 2026, "month_b": 1, "same_author": False},
        ]
        analysis = MODULE.aggregate(pairs)
        self.assertEqual(analysis["within_year"]["n"], 1)
        self.assertEqual(analysis["between_year"]["n"], 1)
        self.assertAlmostEqual(analysis["between_minus_within_mean"], 0.4)

    def test_describe_empty_is_explicit(self) -> None:
        self.assertEqual(MODULE.describe([])["n"], 0)
        self.assertIsNone(MODULE.describe([])["mean"])


if __name__ == "__main__":
    unittest.main()
