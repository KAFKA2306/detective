from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from analyze_zenn_confirmatory_ncd_time_distance import analyze, month_gap, pearson_correlation


class NcdTimeDistanceAnalysisTests(unittest.TestCase):
    def test_month_gap_crosses_year_boundary(self) -> None:
        self.assertEqual(month_gap({"year_a": 2023, "month_a": 12, "year_b": 2024, "month_b": 2}), 2)

    def test_pearson_perfect_positive(self) -> None:
        self.assertAlmostEqual(pearson_correlation([0.0, 1.0, 2.0], [1.0, 2.0, 3.0]), 1.0)

    def test_analysis_separates_same_author(self) -> None:
        report = {
            "source_manifest_sha256": "abc",
            "pairs": [
                {"year_a": 2024, "month_a": 1, "year_b": 2024, "month_b": 2, "same_author": True, "ncd": 0.7},
                {"year_a": 2024, "month_a": 1, "year_b": 2024, "month_b": 3, "same_author": False, "ncd": 0.8},
                {"year_a": 2024, "month_a": 1, "year_b": 2024, "month_b": 4, "same_author": False, "ncd": 0.9},
            ],
        }
        result = analyze(report)
        self.assertEqual(result["analysis"]["same_author_pairs"]["n"], 1)
        self.assertEqual(result["analysis"]["different_author_pairs"]["n"], 2)
        self.assertFalse(result["interpretation"]["inferential_author_effect_claimed"])


if __name__ == "__main__":
    unittest.main()
