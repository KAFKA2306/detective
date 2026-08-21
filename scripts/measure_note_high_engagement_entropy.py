from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html.parser
import json
import math
import pathlib
import random
import statistics
import unicodedata
from collections import Counter, defaultdict

from note_public_page_probe import throttled_fetch

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "reports" / "note_high_engagement_selection.json"
DEFAULT_OUTPUT = ROOT / "reports" / "note_high_engagement_entropy.json"
PREFIX_CHARACTERS = 1000
BOOTSTRAP_REPLICATES = 10000
BOOTSTRAP_SEED = 20260821
EXPECTED_TOTAL = 36


class NoteArticleTextParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if self.depth == 0 and (values.get("data-name") == "body" or "note-common-styles__textnote-body" in classes):
            self.depth = 1
        elif self.depth > 0:
            self.depth += 1
            if tag.lower() in {"script", "style", "noscript"}:
                self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self.depth <= 0:
            return
        if self.skip_depth > 0 and tag.lower() in {"script", "style", "noscript"}:
            self.skip_depth -= 1
        self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth > 0 and self.skip_depth == 0:
            self.parts.append(data)


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def extract_article_text(source: str) -> str:
    parser = NoteArticleTextParser()
    parser.feed(source)
    text = normalize_text(" ".join(parser.parts))
    if not text:
        raise ValueError("public note page does not contain a note article body")
    return text


def shannon_ngram_entropy(text: str, n: int) -> float:
    counts = Counter(text[i : i + n] for i in range(len(text) - n + 1))
    total = sum(counts.values())
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def describe(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "std_population": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "std_population": statistics.pstdev(values),
        "min": min(values),
        "max": max(values),
    }


def hedges_g(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(right) < 2:
        return None
    df = len(left) + len(right) - 2
    pooled = ((len(left) - 1) * statistics.variance(left) + (len(right) - 1) * statistics.variance(right)) / df
    if pooled <= 0:
        return 0.0 if statistics.mean(left) == statistics.mean(right) else None
    d = (statistics.mean(right) - statistics.mean(left)) / math.sqrt(pooled)
    return (1.0 - 3.0 / (4.0 * df - 1.0)) * d


def bootstrap_ci(left: list[float], right: list[float]) -> list[float] | None:
    if not left or not right:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    values = []
    for _ in range(BOOTSTRAP_REPLICATES):
        a = [left[rng.randrange(len(left))] for _ in left]
        b = [right[rng.randrange(len(right))] for _ in right]
        values.append(statistics.mean(b) - statistics.mean(a))
    values.sort()
    return [
        values[math.floor(0.025 * (BOOTSTRAP_REPLICATES - 1))],
        values[math.ceil(0.975 * (BOOTSTRAP_REPLICATES - 1))],
    ]


def validate_selection(selection: dict[str, object]) -> list[dict[str, object]]:
    records = selection.get("records")
    if selection.get("status") != "fixed_before_text_feature_measurement":
        raise ValueError("selection is not frozen before text-feature measurement")
    if selection.get("selected_record_count") != EXPECTED_TOTAL or not isinstance(records, list) or len(records) != EXPECTED_TOTAL:
        raise ValueError("expected 36 selected records")
    if selection.get("selected_by_year") != {"2022": 18, "2026": 18}:
        raise ValueError("expected an 18/18 matched year sample")
    if selection.get("text_features_used_for_selection") is not False:
        raise ValueError("selection must be feature-blind")
    urls = [row.get("source_url") for row in records if isinstance(row, dict)]
    if len(urls) != EXPECTED_TOTAL or len(set(urls)) != EXPECTED_TOTAL:
        raise ValueError("selection contains duplicate or invalid source URLs")
    return records


def audit_row(row: dict[str, object]) -> dict[str, object]:
    url = str(row["source_url"])
    raw = throttled_fetch(url)
    normalized = extract_article_text(raw.decode("utf-8", errors="replace"))
    prefix = normalized[:PREFIX_CHARACTERS]
    enough = len(normalized) >= PREFIX_CHARACTERS
    return {
        "source_url": url,
        "source_url_sha256": row["source_url_sha256"],
        "year": int(row["year"]),
        "month": int(row["month"]),
        "author_sha256": row["author_sha256"],
        "selection_rank_within_year_month": row["rank_within_year_month"],
        "selection_public_reaction_count": row["public_reaction_count"],
        "selection_page_sha256": row["page_sha256"],
        "measurement_page_sha256": hashlib.sha256(raw).hexdigest(),
        "normalized_body_sha256": hashlib.sha256(normalized.encode()).hexdigest(),
        "normalized_body_characters": len(normalized),
        "measurement_status": "measured" if enough else "insufficient_length",
        "measured_characters": PREFIX_CHARACTERS if enough else None,
        "normalized_prefix_sha256": hashlib.sha256(prefix.encode()).hexdigest() if enough else None,
        "char_bigram_entropy_bits": shannon_ngram_entropy(prefix, 2) if enough else None,
        "char_trigram_entropy_bits": shannon_ngram_entropy(prefix, 3) if enough else None,
        "raw_html_persisted": False,
        "article_body_persisted": False,
    }


def aggregate(records: list[dict[str, object]]) -> dict[str, object]:
    measured = [row for row in records if row["measurement_status"] == "measured"]
    by_year: dict[int, list[dict[str, object]]] = defaultdict(list)
    by_month: dict[tuple[int, int], list[dict[str, object]]] = defaultdict(list)
    for row in measured:
        by_year[int(row["year"])].append(row)
        by_month[(int(row["year"]), int(row["month"]))].append(row)
    metrics = ("char_bigram_entropy_bits", "char_trigram_entropy_bits")
    endpoint: dict[str, object] = {"from_year": 2022, "to_year": 2026}
    for metric in metrics:
        left = [float(row[metric]) for row in by_year[2022]]
        right = [float(row[metric]) for row in by_year[2026]]
        endpoint[metric] = {
            "n_2022": len(left),
            "n_2026": len(right),
            "mean_difference_2026_minus_2022": statistics.mean(right) - statistics.mean(left) if left and right else None,
            "mean_difference_bootstrap_95pct_ci": bootstrap_ci(left, right),
            "hedges_g_2026_minus_2022": hedges_g(left, right),
        }
    return {
        "body_length_characters_all_audited": describe([float(int(row["normalized_body_characters"])) for row in records]),
        "measurement_status_counts": {
            status: sum(row["measurement_status"] == status for row in records)
            for status in ("measured", "insufficient_length")
        },
        "by_year": {
            str(year): {metric: describe([float(row[metric]) for row in rows]) for metric in metrics}
            for year, rows in sorted(by_year.items())
        },
        "by_year_month": [
            {
                "year": year,
                "month": month,
                "n": len(rows),
                **{metric: describe([float(row[metric]) for row in rows]) for metric in metrics},
            }
            for (year, month), rows in sorted(by_month.items())
        ],
        "endpoint_comparison": endpoint,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=pathlib.Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    input_bytes = args.input.read_bytes()
    selection = json.loads(input_bytes)
    selected = validate_selection(selection)
    if args.limit is not None:
        selected = selected[: args.limit]

    records: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for index, row in enumerate(selected, start=1):
        try:
            records.append(audit_row(row))
        except Exception as exc:
            errors.append({"source_url": str(row.get("source_url")), "error": f"{type(exc).__name__}: {exc}"})
        print(f"[{index}/{len(selected)}] audited={len(records)} errors={len(errors)}")

    measured = sum(row["measurement_status"] == "measured" for row in records)
    short = sum(row["measurement_status"] == "insufficient_length" for row in records)
    report = {
        "schema_version": 2,
        "measured_at": dt.datetime.now(dt.UTC).isoformat(),
        "source_manifest": str(args.input.relative_to(ROOT)) if args.input.is_relative_to(ROOT) else str(args.input),
        "source_manifest_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "source_metadata_sha256": selection["source_metadata_sha256"],
        "selected_rows_requested": len(selected),
        "audited_rows": len(records),
        "measured_rows": measured,
        "insufficient_length_rows": short,
        "errors": errors,
        "protocol": {
            "normalization": "Unicode NFKC, collapse all whitespace runs to one ASCII space, strip ends",
            "prefix_characters": PREFIX_CHARACTERS,
            "features": [
                "Shannon entropy of overlapping character bigrams",
                "Shannon entropy of overlapping character trigrams",
            ],
            "entropy_log_base": 2,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "insufficient_length_policy": "retain the frozen selected record, report normalized length, do not replace it, and do not compute 1,000-character entropy",
            "raw_html_persisted": False,
            "article_body_persisted": False,
            "selection_recomputed": False,
        },
        "records": records,
        "analysis": aggregate(records) if records else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        key: report[key]
        for key in ("source_manifest_sha256", "selected_rows_requested", "audited_rows", "measured_rows", "insufficient_length_rows", "errors")
    }, ensure_ascii=False, indent=2))
    if errors or len(records) != len(selected):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
