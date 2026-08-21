from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "select_note_high_engagement_sample.py"
SPEC = importlib.util.spec_from_file_location("select_note_high_engagement_sample", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def row(year: int, month: int, reaction: int, slug: str, author: str) -> dict[str, object]:
    url = f"https://note.com/{author}/n/{slug}"
    return {
        "source_url": url,
        "source_url_sha256": hashlib.sha256(url.encode()).hexdigest(),
        "fetched_at": "2026-08-21T00:00:00+00:00",
        "published_at": f"{year}-{month:02d}-15T00:00:00+09:00",
        "public_reaction_count": reaction,
        "page_sha256": "a" * 64,
        "published_in_same_jan_jul_window": True,
    }


class SelectionTests(unittest.TestCase):
    def test_balances_months_using_upper_quartile(self) -> None:
        records: list[dict[str, object]] = []
        for month in range(1, 8):
            records.extend(row(2022, month, i, f"22-{month}-{i}", f"a22{month}{i}") for i in range(1, 9))
            records.extend(row(2026, month, i, f"26-{month}-{i}", f"a26{month}{i}") for i in range(1, 5))
        output = MODULE.select({"records": records, "checked_at": "x"}, "f" * 64)
        self.assertEqual(output["selected_by_year"], {"2022": 7, "2026": 7})
        self.assertEqual(output["selected_record_count"], 14)
        self.assertTrue(all(item["matched_selected_count_per_year"] == 1 for item in output["strata"]))
        self.assertFalse(output["text_features_used_for_selection"])

    def test_equal_reactions_use_source_hash_tie_breaker(self) -> None:
        records: list[dict[str, object]] = []
        for month in range(1, 8):
            for year in (2022, 2026):
                records.extend([
                    row(year, month, 100, f"{year}-{month}-a", f"a{year}{month}a"),
                    row(year, month, 100, f"{year}-{month}-b", f"a{year}{month}b"),
                    row(year, month, 10, f"{year}-{month}-c", f"a{year}{month}c"),
                    row(year, month, 1, f"{year}-{month}-d", f"a{year}{month}d"),
                ])
        output = MODULE.select({"records": records, "checked_at": "x"}, "f" * 64)
        first = [item for item in output["records"] if item["year"] == 2022 and item["month"] == 1][0]
        ties = [item for item in records if item["published_at"].startswith("2022-01") and item["public_reaction_count"] == 100]
        self.assertEqual(first["source_url_sha256"], min(item["source_url_sha256"] for item in ties))

    def test_missing_reaction_and_out_of_window_are_ineligible(self) -> None:
        valid = row(2022, 1, 5, "valid", "valid-author")
        missing = row(2022, 1, 5, "missing", "missing-author")
        missing["public_reaction_count"] = None
        outside = row(2026, 1, 5, "outside", "outside-author")
        outside["published_in_same_jan_jul_window"] = False
        self.assertEqual(MODULE.eligible_records({"records": [valid, missing, outside]}), [valid])


if __name__ == "__main__":
    unittest.main()
