from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from measure_zenn_confirmatory_detector_drift import aggregate, describe


def record(year: int, month: int, probability: float, label: str, feature: float) -> dict[str, object]:
    return {
        "year": year,
        "month": month,
        "probability": probability,
        "label": label,
        "features": {"word_count": feature},
    }


class DetectorDriftTest(unittest.TestCase):
    def test_describe_empty_and_values(self) -> None:
        self.assertEqual(describe([])["n"], 0)
        summary = describe([0.2, 0.4, 0.6])
        self.assertEqual(summary["n"], 3)
        self.assertAlmostEqual(float(summary["mean"]), 0.4)

    def test_aggregate_preserves_year_month_and_labels(self) -> None:
        records = [
            record(2022, 1, 0.20, "Human", 10),
            record(2022, 2, 0.30, "AI", 11),
            record(2026, 1, 0.70, "AI", 12),
            record(2026, 2, 0.80, "AI", 13),
        ]
        result = aggregate(records)
        self.assertEqual(result["feature_names"], ["word_count"])
        self.assertEqual(result["by_year"]["2022"]["label_counts"], {"AI": 1, "Human": 1})
        self.assertEqual(result["by_year"]["2026"]["label_counts"], {"AI": 2})
        self.assertEqual(len(result["by_year_month"]), 4)
        endpoint = result["endpoint"]
        self.assertAlmostEqual(endpoint["mean_probability_difference_2026_minus_2022"], 0.5)
        self.assertIsNotNone(endpoint["mean_probability_difference_bootstrap_95pct_ci"])
        self.assertIsNotNone(endpoint["hedges_g_2026_minus_2022"])

    def test_endpoint_stays_descriptive_with_sparse_year(self) -> None:
        result = aggregate([
            record(2022, 1, 0.2, "Human", 10),
            record(2022, 2, 0.3, "Human", 11),
            record(2026, 1, 0.9, "AI", 12),
        ])
        endpoint = result["endpoint"]
        self.assertEqual(endpoint["n_2026"], 1)
        self.assertIsNone(endpoint["hedges_g_2026_minus_2022"])
        self.assertIn("Detector behavior only", endpoint["interpretation"])


if __name__ == "__main__":
    unittest.main()
