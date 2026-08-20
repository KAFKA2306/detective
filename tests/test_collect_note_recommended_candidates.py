from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "collect_note_recommended_candidates.py"
SPEC = importlib.util.spec_from_file_location("collect_note_recommended_candidates", SCRIPT)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class NoteRecommendedCandidateTest(unittest.TestCase):
    def test_summary_links_keep_only_note_official_article_pages(self) -> None:
        source = '''
        <a href="/info/n/nabc123">roundup</a>
        <a href="https://note.com/info/n/ndef456?x=1">roundup 2</a>
        <a href="/someone/n/narticle">candidate</a>
        <a href="https://example.com/info/n/nope">external</a>
        '''
        self.assertEqual(
            mod.summary_links(source, "https://note.com/info/m/key/archive/2022-01"),
            ["https://note.com/info/n/nabc123", "https://note.com/info/n/ndef456"],
        )

    def test_candidate_links_keep_public_articles_and_exclude_note_official_roundup(self) -> None:
        source = '''
        <a href="https://note.com/alice/n/na1">A</a>
        <a href="/bob/n/nb2?from=roundup">B</a>
        <a href="/info/n/nroundup">self</a>
        <a href="/search?q=x">search</a>
        <a href="/alice/m/magazine">magazine</a>
        '''
        self.assertEqual(
            mod.candidate_links(source, "https://note.com/info/n/nroundup"),
            ["https://note.com/alice/n/na1", "https://note.com/bob/n/nb2"],
        )

    def test_disallowed_collection_paths_are_rejected(self) -> None:
        self.assertFalse(mod.allowed_note_url("https://note.com/api/v3/foo"))
        self.assertFalse(mod.allowed_note_url("https://note.com/search?q=x"))
        self.assertFalse(mod.allowed_note_url("https://example.com/alice/n/na1"))
        self.assertTrue(mod.allowed_note_url("https://note.com/alice/n/na1"))

    def test_source_windows_are_symmetric(self) -> None:
        self.assertEqual(mod.YEARS, (2022, 2026))
        self.assertEqual(mod.MONTHS, tuple(range(1, 8)))
        self.assertEqual(
            mod.archive_url(2022, 1),
            "https://note.com/info/m/m4bd0825e8f53/archive/2022-01",
        )
        self.assertEqual(
            mod.archive_url(2026, 7),
            "https://note.com/info/m/m4bd0825e8f53/archive/2026-07",
        )


if __name__ == "__main__":
    unittest.main()
