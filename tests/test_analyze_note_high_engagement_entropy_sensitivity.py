import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("note_sensitivity", SCRIPTS / "analyze_note_high_engagement_entropy_sensitivity.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class NoteEntropySensitivityTests(unittest.TestCase):
    def test_excludes_missing_record_and_matched_counterpart(self):
        rows = [
            {"year": 2022, "month": 3, "selection_rank_within_year_month": 2, "source_url_sha256": "a", "measurement_status": "insufficient_length", "char_bigram_entropy_bits": None, "char_trigram_entropy_bits": None},
            {"year": 2026, "month": 3, "selection_rank_within_year_month": 2, "source_url_sha256": "b", "measurement_status": "measured", "char_bigram_entropy_bits": 4.0, "char_trigram_entropy_bits": 5.0},
            {"year": 2022, "month": 1, "selection_rank_within_year_month": 1, "source_url_sha256": "c", "measurement_status": "measured", "char_bigram_entropy_bits": 1.0, "char_trigram_entropy_bits": 2.0},
            {"year": 2022, "month": 2, "selection_rank_within_year_month": 1, "source_url_sha256": "d", "measurement_status": "measured", "char_bigram_entropy_bits": 2.0, "char_trigram_entropy_bits": 3.0},
            {"year": 2026, "month": 1, "selection_rank_within_year_month": 1, "source_url_sha256": "e", "measurement_status": "measured", "char_bigram_entropy_bits": 2.0, "char_trigram_entropy_bits": 3.0},
            {"year": 2026, "month": 2, "selection_rank_within_year_month": 1, "source_url_sha256": "f", "measurement_status": "measured", "char_bigram_entropy_bits": 3.0, "char_trigram_entropy_bits": 4.0},
        ]
        result = mod.analyze_pair_complete(rows)
        self.assertEqual(result["analyzed_rows"], 4)
        self.assertEqual(result["comparisons"]["char_bigram_entropy_bits"]["n_2022"], 2)
        self.assertEqual(result["comparisons"]["char_bigram_entropy_bits"]["n_2026"], 2)
        self.assertEqual({row["source_url_sha256"] for row in result["excluded_records"]}, {"a", "b"})


if __name__ == "__main__":
    unittest.main()
