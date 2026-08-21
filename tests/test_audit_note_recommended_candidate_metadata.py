from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "audit_note_recommended_candidate_metadata.py"
SPEC = importlib.util.spec_from_file_location("audit_note_recommended_candidate_metadata", SCRIPT)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class NoteRecommendedCandidateMetadataAuditTest(unittest.TestCase):
    def test_candidate_years_deduplicates_and_preserves_source_years(self) -> None:
        manifest = {
            "by_month": [
                {"year": 2022, "candidate_urls": ["https://note.com/a/n/n1", "https://note.com/b/n/n2"]},
                {"year": 2022, "candidate_urls": ["https://note.com/a/n/n1"]},
                {"year": 2026, "candidate_urls": ["https://note.com/a/n/n1", "https://note.com/c/n/n3"]},
            ]
        }
        self.assertEqual(
            mod.candidate_years(manifest),
            {
                "https://note.com/a/n/n1": {2022, 2026},
                "https://note.com/b/n/n2": {2022},
                "https://note.com/c/n/n3": {2026},
            },
        )

    def test_publication_window_requires_same_source_year_and_january_to_july(self) -> None:
        self.assertTrue(mod.is_same_window((2022, 1), {2022}))
        self.assertTrue(mod.is_same_window((2026, 7), {2026}))
        self.assertFalse(mod.is_same_window((2022, 8), {2022}))
        self.assertFalse(mod.is_same_window((2025, 7), {2026}))
        self.assertFalse(mod.is_same_window(None, {2022}))

    def test_publication_parser_uses_explicit_year_and_month(self) -> None:
        self.assertEqual(mod.parse_publication("2022-03-04T12:34:56.000+09:00"), (2022, 3))
        self.assertEqual(mod.parse_publication("2026-07-31T00:00:00Z"), (2026, 7))
        self.assertIsNone(mod.parse_publication(None))
        self.assertIsNone(mod.parse_publication("not-a-date"))


if __name__ == "__main__":
    unittest.main()
