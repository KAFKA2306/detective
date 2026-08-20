import importlib.util
import math
import pathlib
import sys
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "measure_zenn_confirmatory_entropy.py"
spec = importlib.util.spec_from_file_location("measure_entropy", SCRIPT)
measure = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(measure)


class ConfirmatoryEntropyTests(unittest.TestCase):
    def test_extracts_only_zenn_article_body_and_normalizes_nfkc(self):
        source = """
        <html><body>
          <div>outside</div>
          <article class="foo znc bar"><p>ＡＢＣ</p><p>  D\nE </p><script>ignored</script></article>
          <div>outside too</div>
        </body></html>
        """
        self.assertEqual(measure.extract_article_text(source), "ABC D E")

    def test_bigram_entropy_matches_balanced_two_symbol_distribution(self):
        # Overlapping bigrams: AB, BA, AB, BA -> two equally likely outcomes.
        self.assertAlmostEqual(measure.shannon_ngram_entropy("ABABA", 2), 1.0)

    def test_hedges_g_direction_is_2026_minus_2022(self):
        value = measure.hedges_g([1.0, 2.0, 3.0], [3.0, 4.0, 5.0])
        self.assertIsNotNone(value)
        self.assertGreater(value, 0.0)

    def test_bootstrap_ci_is_deterministic(self):
        left = [1.0, 2.0, 3.0]
        right = [4.0, 5.0, 6.0]
        first = measure.bootstrap_mean_difference_ci(left, right, replicates=1000, seed=7)
        second = measure.bootstrap_mean_difference_ci(left, right, replicates=1000, seed=7)
        self.assertEqual(first, second)
        self.assertIsNotNone(first)
        self.assertLessEqual(first[0], 3.0)
        self.assertGreaterEqual(first[1], 3.0)

    def test_aggregate_keeps_year_month_distribution(self):
        records = [
            {"year": 2022, "month": 1, "char_bigram_entropy_bits": 2.0, "char_trigram_entropy_bits": 3.0},
            {"year": 2022, "month": 2, "char_bigram_entropy_bits": 2.5, "char_trigram_entropy_bits": 3.5},
            {"year": 2026, "month": 1, "char_bigram_entropy_bits": 3.0, "char_trigram_entropy_bits": 4.0},
            {"year": 2026, "month": 2, "char_bigram_entropy_bits": 3.5, "char_trigram_entropy_bits": 4.5},
        ]
        report = measure.aggregate(records)
        self.assertEqual(report["by_year"]["2022"]["char_bigram_entropy_bits"]["n"], 2)
        self.assertEqual(len(report["by_year_month"]), 4)
        self.assertAlmostEqual(
            report["endpoint_comparison"]["char_bigram_entropy_bits"]["mean_difference_2026_minus_2022"],
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
