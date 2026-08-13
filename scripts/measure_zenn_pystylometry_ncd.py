from __future__ import annotations

import collections
import datetime as dt
import html.parser
import json
import pathlib
import statistics
import time
import unicodedata
import urllib.parse
import urllib.request

from pystylometry.authorship import compute_compression_distance

ROOT = pathlib.Path(__file__).resolve().parents[1]
INPUT = ROOT / "corpus" / "zenn_august_sitemap_pilot.jsonl"
OUTPUT = ROOT / "reports" / "zenn_pystylometry_ncd_year_separation.json"
USER_AGENT = "KAFKA2306-detective/0.1 (+https://github.com/KAFKA2306/detective)"
REQUEST_INTERVAL_SECONDS = 0.40
WINDOW = 1000

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


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def fetch_text(url: str) -> str:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < REQUEST_INTERVAL_SECONDS:
        time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
    path = urllib.parse.urlsplit(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1]
    endpoint = f"https://zenn.dev/api/articles/{urllib.parse.quote(slug)}"
    request = urllib.request.Request(endpoint, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    _last_request_at = time.monotonic()
    article = payload.get("article") if isinstance(payload, dict) else None
    if not isinstance(article, dict) or not isinstance(article.get("body_html"), str):
        raise RuntimeError(f"missing body_html: {url}")
    parser = VisibleTextParser()
    parser.feed(article["body_html"])
    value = normalize(parser.text())
    if len(value) < WINDOW:
        raise RuntimeError(f"text shorter than fixed window: {url}")
    return value[:WINDOW]


def main() -> None:
    manifest = [json.loads(line) for line in INPUT.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(manifest) != 60:
        raise RuntimeError(f"expected 60 rows, got {len(manifest)}")

    samples = []
    for idx, row in enumerate(manifest, start=1):
        text = fetch_text(row["source_url"])
        samples.append({"year": int(row["year"]), "url": row["source_url"], "text": text})
        print(f"fetch [{idx}/60] {row['year']} {row['source_url']}")

    nearest_predictions = []
    within = []
    between = []
    pair_count = 0
    for i in range(len(samples)):
        distances = []
        for j in range(len(samples)):
            if i == j:
                continue
            result = compute_compression_distance(samples[i]["text"], samples[j]["text"])
            distance = float(result.ncd)
            distances.append((distance, j))
            if i < j:
                pair_count += 1
                if samples[i]["year"] == samples[j]["year"]:
                    within.append(distance)
                else:
                    between.append(distance)
        distances.sort(key=lambda item: (item[0], samples[item[1]]["url"]))
        best_distance, best_j = distances[0]
        nearest_predictions.append(
            {
                "actual": samples[i]["year"],
                "predicted": samples[best_j]["year"],
                "ncd": best_distance,
            }
        )

    correct = sum(1 for row in nearest_predictions if row["actual"] == row["predicted"])
    accuracy = correct / len(nearest_predictions)
    confusion: dict[str, dict[str, int]] = {}
    years = [2022, 2023, 2024, 2025, 2026]
    for actual in years:
        confusion[str(actual)] = {str(predicted): 0 for predicted in years}
    for row in nearest_predictions:
        confusion[str(row["actual"])][str(row["predicted"])] += 1

    report = {
        "schema_version": 1,
        "status": "measured_not_validated",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "package": "pystylometry",
        "version": "1.4.3",
        "metric": "compute_compression_distance / normalized compression distance",
        "input": {
            "cohort": "august-sitemap-pilot-v2",
            "sample_count": 60,
            "samples_per_year": 12,
            "analysis_window_chars": WINDOW,
            "raw_body_persisted": False,
        },
        "evaluation": {
            "method": "leave-one-out 1-nearest-neighbor by upstream NCD",
            "chance_accuracy_balanced_5_class": 0.2,
            "accuracy": accuracy,
            "correct": correct,
            "total": len(nearest_predictions),
            "confusion_matrix": confusion,
        },
        "pairwise": {
            "pair_count": pair_count,
            "within_year_mean_ncd": statistics.mean(within),
            "within_year_median_ncd": statistics.median(within),
            "between_year_mean_ncd": statistics.mean(between),
            "between_year_median_ncd": statistics.median(between),
        },
        "interpretation_gate": {
            "use_for_year_inference": False,
            "reason": "Pilot evaluation only. Promote only after larger seasonal cohorts and author/topic confound audit reproduce out-of-sample separation.",
        },
        "provenance": {
            "upstream_docs": "https://github.com/craigtrim/pystylometry/blob/main/docs/authorship/compression.md",
            "source": "https://github.com/craigtrim/pystylometry",
        },
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
