import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("note_entropy", SCRIPTS / "measure_note_high_engagement_entropy.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class NoteHighEngagementEntropyTests(unittest.TestCase):
    def test_extracts_note_body_only(self):
        source = '<html><body><h1>outside</h1><div data-name="body" class="note-common-styles__textnote-body"><p>本文 ＡＢＣ</p><script>ignore me</script><p>続き</p></div><footer>outside</footer></body></html>'
        self.assertEqual(mod.extract_article_text(source), "本文 ABC 続き")

    def test_entropy_constant_sequence_is_zero(self):
        self.assertEqual(mod.shannon_ngram_entropy("aaaaaa", 2), 0.0)
        self.assertEqual(mod.shannon_ngram_entropy("aaaaaa", 3), 0.0)

    def test_selection_contract_requires_fixed_36(self):
        rows = [
            {
                "source_url": f"https://note.com/a{i}/n/n{i:02d}",
                "source_url_sha256": str(i),
                "year": 2022 if i < 18 else 2026,
            }
            for i in range(36)
        ]
        selection = {
            "status": "fixed_before_text_feature_measurement",
            "selected_record_count": 36,
            "selected_by_year": {"2022": 18, "2026": 18},
            "text_features_used_for_selection": False,
            "records": rows,
        }
        self.assertEqual(len(mod.validate_selection(selection)), 36)
        selection["text_features_used_for_selection"] = True
        with self.assertRaises(ValueError):
            mod.validate_selection(selection)


if __name__ == "__main__":
    unittest.main()
