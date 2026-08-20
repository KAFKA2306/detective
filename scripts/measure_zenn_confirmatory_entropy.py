from __future__ import annotations

import datetime as dt
import hashlib
import html.parser
import importlib.metadata
import json
import math
import pathlib
import random
import runpy
import statistics
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
INPUT = ROOT / "reports" / "zenn_confirmatory_selection.json"
OUTPUT = ROOT / "reports" / "zenn_confirmatory_entropy.json"
USER_AGENT = "KAFKA2306-detective/0.1 (+https://github.com/KAFKA2306/detective)"
REQUEST_INTERVAL_SECONDS = 0.40
ANALYSIS_WINDOW_CHARS = 1000
EXPECTED_PACKAGE = "pystylometry"
EXPECTED_VERSION = "1.4.3"
BOOTSTRAP_SAMPLES = 5000
BOOTSTRAP_SEED = 20260820

_last_request_at = 0.0


class ZennArticleBodyParser(html.parser.HTMLParser):
    """Extract only the rendered Zenn article body (`.znc`) from a public page."""

    BLOCK_TAGS = {"p", "div", "li", "br", "pre", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr"}
    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.capture_depth = 0
        self.skip_depth = 0
        self.parts: list[str] = []
        self.article_body_found = False

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        attrs_dict = dict(attrs)
        classes = set((attrs_dict.get("class") or "").split())
        if self.capture_depth == 0 and "znc" in classes:
            self.capture_depth = 1
            self.article_body_found = True
            return
        if self.capture_depth == 0:
            return
        self.capture_depth += 1
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        elif self.skip_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.capture_depth == 0:
            return
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif self.skip_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        self.capture_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.capture_depth > 0 and self.skip_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def fetch_public_article(source_url: str) -> str:
    global _last_request_at
    parsed = urllib.parse.urlsplit(source_url)
    if parsed.scheme != "https" or parsed.netloc != "zenn.dev" or "/articles/" not in parsed.path:
        raise RuntimeError(f"refusing non-public-Zenn-article URL: {source_url}")
    if parsed.path.startswith("/api/") or parsed.path == "/search" or parsed.path.startswith("/search/"):
        raise RuntimeError(f"refusing unsupported path: {parsed.path}")
    elapsed = time.monotonic() - _last_request_at
    if elapsed < REQUEST_INTERVAL_SECONDS:
        time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        source = response.read().decode("utf-8", errors="replace")
    _last_request_at = time.monotonic()
    return source


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("empty values")
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)


def summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "std": statistics.pstdev(values),
        "q1": percentile(values, 0.25),
        "q3": percentile(values, 0.75),
        "iqr": percentile(values, 0.75) - percentile(values, 0.25),
        "min": min(values),
        "max": max(values),
    }


def hedges_g(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2 or len(b) < 2:
        return None
    var_a = statistics.variance(a)
    var_b = statistics.variance(b)
    df = len(a) + len(b) - 2
    pooled_var = ((len(a) - 1) * var_a + (len(b) - 1) * var_b) / df
    if pooled_var <= 0:
        return 0.0 if statistics.mean(a) == statistics.mean(b) else None
    d = (statistics.mean(b) - statistics.mean(a)) / math.sqrt(pooled_var)
    correction = 1 - (3 / (4 * df - 1)) if df > 1 else 1.0
    return correction * d


def bootstrap_mean_difference(a: list[float], b: list[float]) -> dict[str, float | int] | None:
    if not a or not b:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    diffs: list[float] = []
    for _ in range(BOOTSTRAP_SAMPLES):
        ra = [a[rng.randrange(len(a))] for _ in a]
        rb = [b[rng.randrange(len(b))] for _ in b]
        diffs.append(statistics.mean(rb) - statistics.mean(ra))
    return {
        "estimate": statistics.mean(b) - statistics.mean(a),
        "ci95_low": percentile(diffs, 0.025),
        "ci95_high": percentile(diffs, 0.975),
        "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "seed": BOOTSTRAP_SEED,
    }


def main() -> None:
    installed = importlib.metadata.version(EXPECTED_PACKAGE)
    if installed != EXPECTED_VERSION:
        raise RuntimeError(f"expected {EXPECTED_PACKAGE}=={EXPECTED_VERSION}, got {installed}")

    analysis_module = runpy.run_path(str(ROOT / "site" / "analyze.py"))
    analyze_text = analysis_module["analyze_text"]
    normalize_text = analysis_module["normalize_text"]

    selection = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = selection.get("selected")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("confirmatory selection has no selected rows")

    measured: list[dict[str, object]] = []
    extraction_errors: dict[str, int] = {}
    for index, row in enumerate(rows, start=1):
        source_url = str(row["source_url"])
        try:
            source = fetch_public_article(source_url)
            parser = ZennArticleBodyParser()
            parser.feed(source)
            if not parser.article_body_found:
                raise RuntimeError("Zenn .znc article body not found")
            normalized = normalize_text(parser.text())
            if len(normalized) < ANALYSIS_WINDOW_CHARS:
                raise RuntimeError(f"normalized article body shorter than {ANALYSIS_WINDOW_CHARS}")
            result = analyze_text(normalized)
            published = dt.datetime.fromisoformat(str(row["published_at"]).replace("Z", "+00:00"))
            measured.append(
                {
                    "source_url_sha256": hashlib.sha256(source_url.encode()).hexdigest(),
                    "author_sha256": row["author_sha256"],
                    "year": published.year,
                    "month": published.month,
                    "content_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                    "char_bigram_entropy": float(result["char_bigram_entropy"]),
                    "char_trigram_entropy": float(result["char_trigram_entropy"]),
                }
            )
            print(f"measured {index}/{len(rows)}")
        except Exception as exc:
            key = f"{type(exc).__name__}: {exc}"
            extraction_errors[key] = extraction_errors.get(key, 0) + 1

    if len(measured) != len(rows):
        raise RuntimeError(f"measured {len(measured)}/{len(rows)} rows; errors={extraction_errors}")

    feature_names = ["char_bigram_entropy", "char_trigram_entropy"]
    by_year: dict[str, dict[str, object]] = {}
    by_month_year: dict[str, dict[str, object]] = {}
    effects: dict[str, dict[str, object]] = {}
    month_directions: dict[str, dict[str, object]] = {}

    for year in range(2022, 2027):
        year_rows = [r for r in measured if r["year"] == year]
        by_year[str(year)] = {
            feature: summary([float(r[feature]) for r in year_rows]) for feature in feature_names
        }

    for year in range(2022, 2027):
        for month in range(1, 8):
            cohort = [r for r in measured if r["year"] == year and r["month"] == month]
            by_month_year[f"{year}-{month:02d}"] = {
                feature: summary([float(r[feature]) for r in cohort]) for feature in feature_names
            }

    for feature in feature_names:
        values_2022 = [float(r[feature]) for r in measured if r["year"] == 2022]
        values_2026 = [float(r[feature]) for r in measured if r["year"] == 2026]
        effects[feature] = {
            "comparison": "2026 minus 2022",
            "mean_difference": bootstrap_mean_difference(values_2022, values_2026),
            "hedges_g": hedges_g(values_2022, values_2026),
        }
        directions: dict[str, object] = {}
        for month in range(1, 8):
            a = [float(r[feature]) for r in measured if r["year"] == 2022 and r["month"] == month]
            b = [float(r[feature]) for r in measured if r["year"] == 2026 and r["month"] == month]
            if not a or not b:
                directions[f"month_{month}"] = {"n_2022": len(a), "n_2026": len(b), "mean_difference": None}
            else:
                diff = statistics.mean(b) - statistics.mean(a)
                directions[f"month_{month}"] = {
                    "n_2022": len(a),
                    "n_2026": len(b),
                    "mean_difference": diff,
                    "direction": "higher_2026" if diff > 0 else "lower_2026" if diff < 0 else "equal",
                }
        month_directions[feature] = directions

    digest_payload = "\n".join(
        json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for r in sorted(measured, key=lambda x: str(x["source_url_sha256"]))
    )
    report = {
        "schema_version": 1,
        "status": "measured_not_causal",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "input": {
            "selection_file": "reports/zenn_confirmatory_selection.json",
            "selected_rows": len(rows),
            "measured_rows": len(measured),
            "analysis_window_chars": ANALYSIS_WINDOW_CHARS,
            "normalization": "Unicode NFKC + collapse whitespace; site/analyze.py",
            "body_source": "public https://zenn.dev/<author>/articles/<slug> HTML .znc content",
            "raw_html_persisted": False,
            "article_body_persisted": False,
        },
        "software": {"pystylometry": installed},
        "features": feature_names,
        "by_year": by_year,
        "by_month_year": by_month_year,
        "effect_2022_to_2026": effects,
        "month_effect_direction": month_directions,
        "measurement_set_sha256": hashlib.sha256(digest_payload.encode()).hexdigest(),
        "extraction_errors": extraction_errors,
        "interpretation": {
            "ai_authorship_inference": False,
            "single_article_year_inference": False,
            "causal_ai_adoption_claim": False,
            "note": "Observed distribution differences are descriptive for the fixed Zenn cohort and do not identify AI authorship or causal effects.",
        },
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compact = {
        "measured_rows": len(measured),
        "measurement_set_sha256": report["measurement_set_sha256"],
        "effect_2022_to_2026": effects,
        "by_year": by_year,
    }
    print("SUMMARY_JSON=" + json.dumps(compact, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
