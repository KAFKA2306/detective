import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "audit_zenn_confirmatory_composition.py"
spec = importlib.util.spec_from_file_location("audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit)


class CompositionAuditTests(unittest.TestCase):
    def test_build_report_tracks_length_and_author_concentration(self):
        selection = {
            "protocol": {"years": [2022, 2023], "months": [1, 2]},
            "selected": [
                {"published_at": "2022-01-01T00:00:00+00:00", "author_sha256": "a", "body_letters_count": 2000},
                {"published_at": "2022-02-01T00:00:00+00:00", "author_sha256": "a", "body_letters_count": 3000},
                {"published_at": "2023-01-01T00:00:00+00:00", "author_sha256": "b", "body_letters_count": 4000},
                {"published_at": "2023-02-01T00:00:00+00:00", "author_sha256": "a", "body_letters_count": 5000},
            ],
        }
        report = audit.build_report(selection)
        self.assertEqual(report["selected_rows"], 4)
        self.assertEqual(report["length_all"]["median"], 3500.0)
        self.assertEqual(report["author_concentration"]["unique_authors"], 2)
        self.assertEqual(report["author_concentration"]["max_articles_per_author"], 3)
        self.assertEqual(report["author_concentration"]["authors_present_in_multiple_years"], 1)
        self.assertEqual(report["strata"][0]["selected"], 1)

    def test_empty_stratum_is_explicit(self):
        selection = {
            "protocol": {"years": [2022], "months": [1, 2]},
            "selected": [
                {"published_at": "2022-01-01T00:00:00+00:00", "author_sha256": "a", "body_letters_count": 2000}
            ],
        }
        report = audit.build_report(selection)
        february = report["strata"][1]
        self.assertEqual(february["selected"], 0)
        self.assertEqual(february["unique_authors"], 0)
        self.assertIsNone(february["length"]["mean"])


if __name__ == "__main__":
    unittest.main()
