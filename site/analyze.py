from __future__ import annotations

import json
import math
import unicodedata

from pystylometry.ngrams import compute_character_bigram_entropy, compute_ngram_entropy

ANALYSIS_WINDOW_CHARS = 1000
ANALYSIS_NORMALIZATION = "Unicode NFKC + collapse whitespace"


def normalize_text(text: str) -> str:
    """Normalize corpus and pasted text identically before stylometry."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _finite(value: float) -> float | None:
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def analyze_text(text: str) -> dict[str, float | int | None]:
    """Run the canonical browser/offline analysis on a fixed-length text window."""
    normalized = normalize_text(text)
    if len(normalized) < ANALYSIS_WINDOW_CHARS:
        raise ValueError(
            f"判定には正規化後 {ANALYSIS_WINDOW_CHARS} 文字以上が必要です。"
            f"現在は {len(normalized)} 文字です。"
        )

    window = normalized[:ANALYSIS_WINDOW_CHARS]
    bigram = compute_character_bigram_entropy(window)
    trigram = compute_ngram_entropy(window, n=3, ngram_type="character")
    return {
        "normalized_char_count": len(normalized),
        "analyzed_char_count": len(window),
        "char_bigram_entropy": _finite(bigram.entropy),
        "char_bigram_perplexity": _finite(bigram.perplexity),
        "char_bigram_total": int(bigram.metadata.get("total_ngrams", 0)),
        "char_bigram_unique": int(bigram.metadata.get("total_unique_ngrams", 0)),
        "char_trigram_entropy": _finite(trigram.entropy),
        "char_trigram_perplexity": _finite(trigram.perplexity),
        "char_trigram_total": int(trigram.metadata.get("total_ngrams", 0)),
        "char_trigram_unique": int(trigram.metadata.get("total_unique_ngrams", 0)),
    }


def detective_analyze_json(text: str) -> str:
    return json.dumps(analyze_text(text), ensure_ascii=False, allow_nan=False)
