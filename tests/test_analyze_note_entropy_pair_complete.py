import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("note_entropy_pair_complete", SCRIPTS / "analyze_note_entropy_pair_complete.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def make_report():
    records = []
    for year in (2022, 2026):
        for index in range(18):
            month = 3 if index < 3 else ((index - 3) % 6) + 1
            rank = index + 1 if index < 3 else ((index - 3) // 6) + 1
            records.append(
                {
                    "source_url_sha256": f"{year}-{index}",
                    "year": year,
                    "month": month,
                    "selection_rank_within_year_month": rank,
                    "normalized_body_characters": 2000,
                    "measurement_status": "measured",
                    "char_bigram_entropy_bits": 8.0 + (0.1 if year == 2026 else 0.0) + index / 1000,
                    "char_trigram_entropy_bits": 9.0 + (0.05 if year == 2026 else 0.0) + index / 1000,
                }
            )
    short = next(row for row in records if row["year"] == 2022 and row["month"] == 3 and row["selection_rank_within_year_month"] == 2)
    short.update(
        normalized_body_characters=121,
        measurement_status="insufficient_length",
        char_bigram_entropy_bits=None,
        char_trigram_entropy_bits=None,
    )
    return {
        "selected_rows_requested": 36,
        "errors": [],
        "source_manifest_sha256": "selection-sha",
        "records": records,
    }


class NoteEntropyPairCompleteTests(unittest.TestCase):
    def test_removes_only_matching_measured_counterpart(self):
        selected, missing, counterpart = mod.validate_and_select_pair_complete(make_report())
        self.assertEqual((missing["year"], missing["month"], missing["selection_rank_within_year_month"]), (2022, 3, 2))
        self.assertEqual((counterpart["year"], counterpart["month"], counterpart["selection_rank_within_year_month"]), (2026, 3, 2))
        self.assertEqual(sum(row["year"] == 2022 for row in selected), 17)
        self.assertEqual(sum(row["year"] == 2026 for row in selected), 17)

    def test_build_summary_keeps_selection_feature_blind(self):
        summary = mod.build_summary(make_report(), "entropy-sha")
        self.assertFalse(summary["text_features_used_to_choose_counterpart"])
        self.assertEqual(summary["analysis"]["n_2022"], 17)
        self.assertEqual(summary["analysis"]["n_2026"], 17)
        self.assertEqual(summary["source_entropy_report_sha256"], "entropy-sha")

    def test_rejects_multiple_insufficient_records(self):
        report = make_report()
        measured = next(row for row in report["records"] if row["year"] == 2022 and row["measurement_status"] == "measured")
        measured["measurement_status"] = "insufficient_length"
        with self.assertRaises(ValueError):
            mod.validate_and_select_pair_complete(report)


if __name__ == "__main__":
    unittest.main()
