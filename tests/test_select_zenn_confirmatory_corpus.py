import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "select_zenn_confirmatory_corpus.py"
spec = importlib.util.spec_from_file_location("selector", SCRIPT)
selector = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(selector)


def row(slug: str, published_at: str, author: str, body_letters_count: int = 1600, article_type: str = "tech"):
    return {
        "source_url": f"https://zenn.dev/example/articles/{slug}",
        "published_at": published_at,
        "author_sha256": author,
        "body_letters_count": body_letters_count,
        "article_type": article_type,
    }


class ConfirmatoryCorpusSelectorTest(unittest.TestCase):
    def test_protocol_has_35_strata_and_excludes_august(self):
        result = selector.select([
            row("jan", "2022-01-01T00:00:00+09:00", "a"),
            row("aug", "2022-08-01T00:00:00+09:00", "b"),
        ])
        self.assertEqual(35, len(result["strata"]))
        self.assertEqual(1, result["selected_rows"])
        self.assertEqual(1, result["rejection_reasons"]["outside_confirmatory_window"])
        self.assertTrue(result["protocol"]["feature_blind_selection"])
        self.assertTrue(result["protocol"]["august_pilot_excluded"])

    def test_one_article_per_author_per_stratum_and_shortfall_is_preserved(self):
        rows = [
            row("a1", "2023-03-01T00:00:00+09:00", "same-author"),
            row("a2", "2023-03-02T00:00:00+09:00", "same-author"),
            row("b1", "2023-03-03T00:00:00+09:00", "other-author"),
        ]
        result = selector.select(rows)
        march = next(item for item in result["strata"] if item["year"] == 2023 and item["month"] == 3)
        self.assertEqual(3, march["eligible_candidates"])
        self.assertEqual(2, march["unique_authors"])
        self.assertEqual(2, march["selected"])
        self.assertEqual(10, march["shortfall"])

    def test_selection_is_independent_of_input_order(self):
        rows = [
            row("one", "2024-05-01T00:00:00+09:00", "a"),
            row("two", "2024-05-02T00:00:00+09:00", "b"),
            row("three", "2024-05-03T00:00:00+09:00", "c"),
        ]
        first = selector.select(rows)["selected"]
        second = selector.select(list(reversed(rows)))["selected"]
        self.assertEqual(
            [item["source_url"] for item in first],
            [item["source_url"] for item in second],
        )

    def test_rejects_non_tech_short_and_non_zenn_rows(self):
        rows = [
            row("short", "2025-07-01T00:00:00+09:00", "a", body_letters_count=1499),
            row("idea", "2025-07-02T00:00:00+09:00", "b", article_type="idea"),
            {
                **row("foreign", "2025-07-03T00:00:00+09:00", "c"),
                "source_url": "https://example.com/article",
            },
        ]
        result = selector.select(rows)
        self.assertEqual(0, result["selected_rows"])
        self.assertEqual(1, result["rejection_reasons"]["body_too_short"])
        self.assertEqual(1, result["rejection_reasons"]["not_tech"])
        self.assertEqual(1, result["rejection_reasons"]["not_zenn_url"])


if __name__ == "__main__":
    unittest.main()
