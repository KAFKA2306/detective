from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import statistics
from collections import defaultdict

from measure_note_high_engagement_entropy import (
    PREFIX_CHARACTERS,
    extract_article_text,
    validate_selection,
)
from note_public_page_probe import throttled_fetch

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "reports" / "note_high_engagement_selection.json"
DEFAULT_OUTPUT = ROOT / "reports" / "note_high_engagement_ncd.json"
PYSTYLOMETRY_VERSION = "1.4.3"


def load_compute_compression_distance():
    try:
        from pystylometry.authorship import compute_compression_distance
    except ImportError as exc:
        raise RuntimeError(
            f"pystylometry=={PYSTYLOMETRY_VERSION} is required; run with "
            f"`uv run --with pystylometry=={PYSTYLOMETRY_VERSION} ...`"
        ) from exc
    return compute_compression_distance


def fetch_prefix(row: dict[str, object]) -> dict[str, object]:
    url = str(row["source_url"])
    raw = throttled_fetch(url)
    normalized = extract_article_text(raw.decode("utf-8", errors="replace"))
    enough = len(normalized) >= PREFIX_CHARACTERS
    prefix = normalized[:PREFIX_CHARACTERS] if enough else ""
    return {
        "source_url": url,
        "source_url_sha256": row["source_url_sha256"],
        "year": int(row["year"]),
        "month": int(row["month"]),
        "author_sha256": row["author_sha256"],
        "selection_rank_within_year_month": row["rank_within_year_month"],
        "measurement_page_sha256": hashlib.sha256(raw).hexdigest(),
        "normalized_body_sha256": hashlib.sha256(normalized.encode()).hexdigest(),
        "normalized_body_characters": len(normalized),
        "measurement_status": "measured" if enough else "insufficient_length",
        "normalized_prefix_sha256": hashlib.sha256(prefix.encode()).hexdigest() if enough else None,
        "text": prefix if enough else None,
    }


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


def compute_pairs(records: list[dict[str, object]], compute_distance) -> list[dict[str, object]]:
    pairs: list[dict[str, object]] = []
    for i, left in enumerate(records):
        for right in records[i + 1 :]:
            result = compute_distance(str(left["text"]), str(right["text"]))
            pairs.append(
                {
                    "left_prefix_sha256": left["normalized_prefix_sha256"],
                    "right_prefix_sha256": right["normalized_prefix_sha256"],
                    "year_a": left["year"],
                    "month_a": left["month"],
                    "year_b": right["year"],
                    "month_b": right["month"],
                    "same_author": left["author_sha256"] == right["author_sha256"],
                    "ncd": float(result.ncd),
                }
            )
    return pairs


def aggregate(pairs: list[dict[str, object]]) -> dict[str, object]:
    within_year: list[float] = []
    between_year: list[float] = []
    by_year_pair: dict[tuple[int, int], list[float]] = defaultdict(list)
    for row in pairs:
        value = float(row["ncd"])
        year_a = int(row["year_a"])
        year_b = int(row["year_b"])
        (within_year if year_a == year_b else between_year).append(value)
        by_year_pair[tuple(sorted((year_a, year_b)))].append(value)
    return {
        "overall": describe([float(row["ncd"]) for row in pairs]),
        "within_year": describe(within_year),
        "between_year": describe(between_year),
        "between_minus_within_mean": (
            statistics.mean(between_year) - statistics.mean(within_year)
            if within_year and between_year
            else None
        ),
        "by_year_pair": [
            {"year_a": a, "year_b": b, **describe(values)}
            for (a, b), values in sorted(by_year_pair.items())
        ],
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

    audited: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for index, row in enumerate(selected, start=1):
        try:
            audited.append(fetch_prefix(row))
        except Exception as exc:
            errors.append({"source_url": str(row.get("source_url")), "error": f"{type(exc).__name__}: {exc}"})
        print(f"[{index}/{len(selected)}] audited={len(audited)} errors={len(errors)}")

    if errors or len(audited) != len(selected):
        raise SystemExit(json.dumps({"errors": errors, "audited": len(audited), "requested": len(selected)}, ensure_ascii=False))

    measured = [row for row in audited if row["measurement_status"] == "measured"]
    compute_distance = load_compute_compression_distance()
    pairs = compute_pairs(measured, compute_distance)
    public_records = [{key: value for key, value in row.items() if key != "text"} for row in audited]
    report = {
        "schema_version": 1,
        "measured_at": dt.datetime.now(dt.UTC).isoformat(),
        "source_manifest": str(args.input.relative_to(ROOT)) if args.input.is_relative_to(ROOT) else str(args.input),
        "source_manifest_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "selected_rows_requested": len(selected),
        "audited_rows": len(audited),
        "measured_rows": len(measured),
        "insufficient_length_rows": len(audited) - len(measured),
        "pair_count": len(pairs),
        "errors": errors,
        "protocol": {
            "package": "pystylometry",
            "package_version": PYSTYLOMETRY_VERSION,
            "function": "pystylometry.authorship.compute_compression_distance",
            "normalization": "Unicode NFKC, collapse all whitespace runs to one ASCII space, strip ends",
            "prefix_characters": PREFIX_CHARACTERS,
            "insufficient_length_policy": "retain frozen selection row, report length, exclude it from 1,000-character NCD without replacement",
            "raw_html_persisted": False,
            "article_body_persisted": False,
            "selection_recomputed": False,
            "interpretation": "cohort similarity measurement; not a single-article publication-year classifier",
        },
        "records": public_records,
        "pairs": pairs,
        "analysis": aggregate(pairs),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "source_manifest_sha256": report["source_manifest_sha256"],
        "audited_rows": report["audited_rows"],
        "measured_rows": report["measured_rows"],
        "insufficient_length_rows": report["insufficient_length_rows"],
        "pair_count": report["pair_count"],
        "analysis": report["analysis"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
