from __future__ import annotations

import datetime as dt
import hashlib
import html.parser
import json
import math
import pathlib
import statistics
import time
import unicodedata
import urllib.parse
import urllib.request

from pystylometry.ngrams import compute_character_bigram_entropy, compute_ngram_entropy

ROOT = pathlib.Path(__file__).resolve().parents[1]
INPUT = ROOT / "corpus" / "zenn_august_sitemap_pilot.jsonl"
METRICS_OUTPUT = ROOT / "corpus" / "zenn_august_pystylometry_metrics.jsonl"
BASELINE_OUTPUT = ROOT / "site" / "data" / "baselines.json"
USER_AGENT = "KAFKA2306-detective/0.1 (+https://github.com/KAFKA2306/detective)"
PACKAGE = "pystylometry"
PACKAGE_VERSION = "1.4.3"
REQUEST_INTERVAL_SECONDS = 0.40

_last_request_at = 0.0


class VisibleTextParser(html.parser.HTMLParser):
    """Extract visible article text without persisting source HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
        elif self.skip_depth == 0 and tag in {"p", "div", "li", "br", "pre", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        elif self.skip_depth == 0 and tag in {"p", "div", "li", "pre", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def normalize_text(text: str) -> str:
    """Canonical normalization shared conceptually with the Pyodide worker."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def fetch_detail(source_url: str) -> dict:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < REQUEST_INTERVAL_SECONDS:
        time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
    path = urllib.parse.urlsplit(source_url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1]
    endpoint = f"https://zenn.dev/api/articles/{urllib.parse.quote(slug)}"
    request = urllib.request.Request(endpoint, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    _last_request_at = time.monotonic()
    article = payload.get("article") if isinstance(payload, dict) else None
    if not isinstance(article, dict):
        raise RuntimeError(f"no article detail for {source_url}")
    detail_path = article.get("path")
    if isinstance(detail_path, str) and detail_path != path:
        raise RuntimeError(f"path mismatch for {source_url}: {detail_path}")
    return article


def finite(value: float) -> float | None:
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def analyze(text: str) -> dict[str, float | int | None]:
    normalized = normalize_text(text)
    bigram = compute_character_bigram_entropy(normalized)
    trigram = compute_ngram_entropy(normalized, n=3, ngram_type="character")
    return {
        "normalized_char_count": len(normalized),
        "char_bigram_entropy": finite(bigram.entropy),
        "char_bigram_perplexity": finite(bigram.perplexity),
        "char_bigram_total": int(bigram.metadata.get("total_ngrams", 0)),
        "char_bigram_unique": int(bigram.metadata.get("total_unique_ngrams", 0)),
        "char_trigram_entropy": finite(trigram.entropy),
        "char_trigram_perplexity": finite(trigram.perplexity),
        "char_trigram_total": int(trigram.metadata.get("total_ngrams", 0)),
        "char_trigram_unique": int(trigram.metadata.get("total_unique_ngrams", 0)),
    }


def metric_summary(values: list[float]) -> dict[str, float | int]:
    if len(values) < 2:
        raise RuntimeError("at least two samples are required for a baseline metric")
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "std": statistics.stdev(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


def main() -> None:
    source_rows = [json.loads(line) for line in INPUT.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not source_rows:
        raise SystemExit("metadata pilot is empty")

    generated_at = dt.datetime.now(dt.UTC).isoformat()
    output_rows: list[dict] = []
    for index, row in enumerate(source_rows, start=1):
        source_url = row["source_url"]
        article = fetch_detail(source_url)
        body_html = article.get("body_html")
        if not isinstance(body_html, str) or not body_html:
            raise RuntimeError(f"body_html missing for {source_url}")
        parser = VisibleTextParser()
        parser.feed(body_html)
        visible_text = parser.text()
        metrics = analyze(visible_text)
        if metrics["normalized_char_count"] < 100:
            raise RuntimeError(f"visible text too short for {source_url}")
        output_rows.append(
            {
                "schema_version": 1,
                "source_url": source_url,
                "year": int(row["year"]),
                "cohort": row["cohort"],
                "published_at": row["published_at"],
                "fetched_at": generated_at,
                "content_sha256": hashlib.sha256(body_html.encode("utf-8")).hexdigest(),
                "extractor": "stdlib.HTMLParser visible text; script/style/noscript excluded",
                "normalization": "Unicode NFKC + collapse whitespace",
                "detector": f"{PACKAGE}=={PACKAGE_VERSION}",
                "metrics": metrics,
            }
        )
        # body_html and visible_text are intentionally not persisted.
        print(f"[{index}/{len(source_rows)}] {row['year']} {source_url} chars={metrics['normalized_char_count']}")

    METRICS_OUTPUT.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in output_rows),
        encoding="utf-8",
    )

    years = sorted({int(row["year"]) for row in output_rows})
    expected_years = [2022, 2023, 2024, 2025, 2026]
    if years != expected_years:
        raise RuntimeError(f"unexpected years: {years}")
    sample_counts = {str(year): sum(1 for row in output_rows if row["year"] == year) for year in years}
    if len(set(sample_counts.values())) != 1 or min(sample_counts.values()) < 10:
        raise RuntimeError(f"unbalanced/insufficient pilot: {sample_counts}")

    baseline_metrics: dict[str, dict[str, dict]] = {}
    for key in ("char_bigram_entropy", "char_trigram_entropy"):
        baseline_metrics[key] = {}
        for year in years:
            values = [
                float(row["metrics"][key])
                for row in output_rows
                if row["year"] == year and row["metrics"].get(key) is not None
            ]
            baseline_metrics[key][str(year)] = metric_summary(values)

    baseline = {
        "schema_version": 2,
        "status": "pilot_ready",
        "cohort": "august-sitemap-pilot",
        "years": years,
        "generated_at": generated_at,
        "sample_counts": sample_counts,
        "distance_metrics": ["char_bigram_entropy", "char_trigram_entropy"],
        "distance_method": "RMS of per-year z-scores; descriptive pilot only",
        "metrics": baseline_metrics,
        "detector": {
            "package": PACKAGE,
            "version": PACKAGE_VERSION,
            "functions": ["compute_character_bigram_entropy", "compute_ngram_entropy(character,n=3)"],
        },
        "preprocessing": {
            "source": "article.body_html fetched transiently",
            "extractor": "stdlib.HTMLParser visible text; script/style/noscript excluded",
            "normalization": "Unicode NFKC + collapse whitespace",
            "raw_body_persisted": False,
        },
        "provenance": [
            "corpus/zenn_august_sitemap_pilot.jsonl",
            "corpus/zenn_august_pystylometry_metrics.jsonl",
            "reports/zenn_august_sitemap_pilot_summary.json",
            "reports/zenn_article_sitemap_inventory.json",
        ],
        "limitations": [
            "12 samples per year",
            "same-season August pilot, not full-year distribution",
            "sitemap lastmod was used only for candidate discovery and may create edit-history selection bias",
            "distance is not evidence of AI authorship",
        ],
    }
    BASELINE_OUTPUT.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(baseline, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
