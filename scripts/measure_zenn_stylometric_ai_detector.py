from __future__ import annotations

import datetime as dt
import hashlib
import html.parser
import json
import pathlib
import statistics
import time
import unicodedata
import urllib.parse
import urllib.request

from stylometric_ai_detector import extract_stylometric_features, predict

ROOT = pathlib.Path(__file__).resolve().parents[1]
INPUT = ROOT / "corpus" / "zenn_august_sitemap_pilot.jsonl"
OUTPUT = ROOT / "reports" / "zenn_stylometric_ai_detector_2026_measurement.json"
USER_AGENT = "KAFKA2306-detective/0.1 (+https://github.com/KAFKA2306/detective)"
REQUEST_INTERVAL_SECONDS = 0.40
PACKAGE = "stylometric-ai-detector"
VERSION = "0.2.4"
ANALYSIS_WINDOW_CHARS = 1000

_last_request_at = 0.0


class VisibleTextParser(html.parser.HTMLParser):
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
    return article


def summary(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    n = len(ordered)
    if n < 2:
        raise RuntimeError("at least two observations required")
    q1 = ordered[(n - 1) // 4]
    q3 = ordered[(3 * (n - 1)) // 4]
    return {
        "n": n,
        "mean": statistics.mean(ordered),
        "median": statistics.median(ordered),
        "std": statistics.stdev(ordered),
        "min": min(ordered),
        "max": max(ordered),
        "iqr": q3 - q1,
    }


def main() -> None:
    source_rows = [json.loads(line) for line in INPUT.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(source_rows) != 60:
        raise RuntimeError(f"expected fixed 60-row pilot, got {len(source_rows)}")

    measured: list[dict] = []
    generated_at = dt.datetime.now(dt.UTC).isoformat()
    for index, row in enumerate(source_rows, start=1):
        article = fetch_detail(row["source_url"])
        body_html = article.get("body_html")
        if not isinstance(body_html, str) or not body_html:
            raise RuntimeError(f"body_html missing for {row['source_url']}")
        parser = VisibleTextParser()
        parser.feed(body_html)
        normalized = normalize_text(parser.text())
        if len(normalized) < ANALYSIS_WINDOW_CHARS:
            raise RuntimeError(f"normalized text shorter than fixed window: {row['source_url']}")
        window = normalized[:ANALYSIS_WINDOW_CHARS]

        features = extract_stylometric_features(window)
        prediction = predict(text=window)
        if not isinstance(features, dict) or not isinstance(prediction, dict):
            raise RuntimeError("unexpected upstream return type")

        measured.append(
            {
                "year": int(row["year"]),
                "source_url": row["source_url"],
                "content_sha256": hashlib.sha256(body_html.encode("utf-8")).hexdigest(),
                "features": {key: float(value) for key, value in features.items()},
                "prediction": {
                    "label": str(prediction.get("label")),
                    "probability": float(prediction.get("probability")),
                },
            }
        )
        print(f"[{index}/{len(source_rows)}] {row['year']} {prediction}")

    years = [2022, 2023, 2024, 2025, 2026]
    feature_names = sorted(measured[0]["features"])
    by_year: dict[str, dict] = {}
    for year in years:
        rows = [row for row in measured if row["year"] == year]
        if len(rows) != 12:
            raise RuntimeError(f"{year}: expected 12 rows, got {len(rows)}")
        by_year[str(year)] = {
            "sample_count": len(rows),
            "features": {
                key: summary([float(row["features"][key]) for row in rows]) for key in feature_names
            },
            "upstream_ai_probability": summary([float(row["prediction"]["probability"]) for row in rows]),
            "upstream_label_counts": {
                label: sum(1 for row in rows if row["prediction"]["label"] == label)
                for label in sorted({row["prediction"]["label"] for row in rows})
            },
        }

    report = {
        "schema_version": 1,
        "status": "measured_not_validated",
        "generated_at": generated_at,
        "package": PACKAGE,
        "version": VERSION,
        "upstream_role": "2026 lightweight stylometric AI/Human benchmark",
        "input": {
            "cohort": "august-sitemap-pilot-v2",
            "years": years,
            "samples_per_year": 12,
            "analysis_window_chars": ANALYSIS_WINDOW_CHARS,
            "normalization": "Unicode NFKC + collapse whitespace; same contract as site/analyze.py",
            "raw_body_persisted": False,
        },
        "feature_names": feature_names,
        "years": by_year,
        "interpretation_gate": {
            "use_for_ai_authorship": False,
            "use_for_year_inference": False,
            "reason": "Upstream explicitly documents English-only, single-dataset, pre-2024 training and warns against cross-language/domain/model-generation generalization. Japanese outputs are retained only as observed benchmark behavior.",
        },
        "provenance": {
            "pypi": "https://pypi.org/project/stylometric-ai-detector/0.2.4/",
            "source": "https://github.com/dinis-a/stylometric-ai-detector",
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
