from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from build_zenn_confirmatory_research_summary import build, includes_zero


class ConfirmatoryResearchSummaryTests(unittest.TestCase):
    def test_interval_zero_check(self) -> None:
        self.assertTrue(includes_zero([-1.0, 2.0]))
        self.assertFalse(includes_zero([0.1, 2.0]))

    def test_rejects_mixed_source_manifests(self) -> None:
        composition = {
            "selected_rows": 1,
            "author_concentration": {"unique_authors": 1, "authors_present_in_multiple_years": 0},
            "length_by_year": {"2026": {"n": 0}},
        }
        entropy = {
            "source_manifest_sha256": "a",
            "measured_rows": 1,
            "endpoint_comparison_2026_minus_2022": {
                "char_bigram_entropy_bits": {"mean_difference": 0.0, "bootstrap_95pct_ci": [-1.0, 1.0]},
                "char_trigram_entropy_bits": {"mean_difference": 0.0, "bootstrap_95pct_ci": [-1.0, 1.0]},
            },
        }
        ncd = {
            "source_manifest_sha256": "b",
            "source_pair_count": 0,
            "analysis": {
                "all_pairs": {"month_gap_range": None, "month_gap_ncd_pearson_r": None},
                "different_author_pairs": {"month_gap_ncd_pearson_r": None},
                "same_author_pairs": {"n": 0},
            },
            "interpretation": {"inferential_author_effect_claimed": False},
        }
        detector = {
            "source_manifest_sha256": "a",
            "measured_rows": 1,
            "package": "example",
            "version": "1",
            "errors": [],
            "label_counts": {},
            "endpoint_2026_minus_2022": {"mean_difference": 0.0, "bootstrap_95pct_ci": [-1.0, 1.0]},
            "artifact_sha256": "x",
        }
        with self.assertRaises(ValueError):
            build(composition, entropy, ncd, detector)


if __name__ == "__main__":
    unittest.main()
