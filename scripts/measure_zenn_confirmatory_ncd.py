from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import statistics
from collections import defaultdict

from measure_zenn_confirmatory_entropy import PREFIX_CHARACTERS, extract_article_text
from zenn_public_page_probe import fetch

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "reports" / "zenn_confirmatory_selection.json"
DEFAULT_OUTPUT = ROOT / "reports" / "zenn_confirmatory_ncd.json"
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
    source = fetch(url, sitemap=False).decode("utf-8", errors="replace")
    normalized = extract_article_text(source)
    if len(normalized) < PREFIX_CHARACTERS:
        raise ValueError(f"normalized article body shorter than {PREFIX_CHARACTERS} characters: {url}")
    prefix = normalized[:PREFIX_CHARACTERS]
    published_at = dt.datetime.fromisoformat(str(row["published_at"]).replace("Z", "+00:00"))
    return {
        "source_url": url,
        "published_at": published_at.isoformat(),
        "year": published_at.year,
        "month": published_at.month,
        "author_sha256": str(row["author_sha256"]),
        "selection_rank_sha256": str(row["selection_rank_sha256"]),
        "normalized_prefix_sha256": hashlib.sha256(prefix.encode()).hexdigest(),
        "text": prefix,
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


def aggregate(pairs: list[dict[str, object]]) -> dict[str, object]:
    within_year: list[float] = []
    between_year: list[float] = []
    same_author: list[float] = []
    different_author: list[float] = []
    by_year_pair: dict[tuple[int, int], list[float]] = defaultdict(list)
    by_month_gap: dict[int, list[float]] = defaultdict(list)

    for pair in pairs:
        ncd = float(pair["ncd"])
        year_a = int(pair["year_a"])
        year_b = int(pair["year_b"])
        if year_a == year_b:
            within_year.append(ncd)
        else:
            between_year.append(ncd)
        if pair["same_author"]:
            same_author.append(ncd)
        else:
            different_author.append(ncd)
        by_year_pair[tuple(sorted((year_a, year_b)))].append(ncd)
        month_index_a = year_a * 12 + int(pair["month_a"])
        month_index_b = year_b * 12 + int(pair["month_b"])
        by_month_gap[abs(month_index_b - month_index_a)].append(ncd)

    return {
        "overall": describe([float(pair["ncd"]) for pair in pairs]),
        "within_year": describe(within_year),
        "between_year": describe(between_year),
        "same_author": describe(same_author),
        "different_author": describe(different_author),
        "by_year_pair": [
            {"year_a": a, "year_b": b, **describe(values)}
            for (a, b), values in sorted(by_year_pair.items())
        ],
        "by_month_gap": [
            {"month_gap": gap, **describe(values)} for gap, values in sorted(by_month_gap.items())
        ],
    }


def compute_pairs(records: list[dict[str, object]], compute_distance) -> list[dict[str, object]]:
    pairs: list[dict[str, object]] = []
    total = len(records) * (len(records) - 1) // 2
    done = 0
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
            done += 1
            if done % 1000 == 0 or done == total:
                print(f"pairwise NCD {done}/{total}")
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=pathlib.Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    input_bytes = args.input.read_bytes()
    selection = json.loads(input_bytes)
    selected = list(selection["selected"])
    if args.limit is not None:
        selected = selected[: args.limit]

    records: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for index, row in enumerate(selected, start=1):
        try:
            records.append(fetch_prefix(row))
        except Exception as exc:
            errors.append({"source_url": str(row.get("source_url")), "error": f"{type(exc).__name__}: {exc}"})
        print(f"[{index}/{len(selected)}] fetched={len(records)} errors={len(errors)}")

    if errors or len(records) != len(selected):
        raise SystemExit(json.dumps({"errors": errors, "fetched": len(records), "requested": len(selected)}, ensure_ascii=False))

    compute_distance = load_compute_compression_distance()
    pairs = compute_pairs(records, compute_distance)
    public_records = [{key: value for key, value in row.items() if key != "text"} for row in records]
    report = {
        "schema_version": 1,
        "measured_at": dt.datetime.now(dt.UTC).isoformat(),
        "source_manifest": str(args.input.relative_to(ROOT)) if args.input.is_relative_to(ROOT) else str(args.input),
        "source_manifest_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "selected_rows_requested": len(selected),
        "measured_rows": len(records),
        "pair_count": len(pairs),
        "errors": errors,
        "protocol": {
            "package": "pystylometry",
            "package_version": PYSTYLOMETRY_VERSION,
            "function": "pystylometry.authorship.compute_compression_distance",
            "normalization": "Unicode NFKC, collapse all whitespace runs to one ASCII space, strip ends",
            "prefix_characters": PREFIX_CHARACTERS,
            "raw_html_persisted": False,
            "article_body_persisted": False,
            "interpretation": "cohort similarity auxiliary measurement; not a single-article publication-year classifier",
        },
        "records": public_records,
        "pairs": pairs,
        "analysis": aggregate(pairs),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "source_manifest_sha256": report["source_manifest_sha256"],
        "measured_rows": report["measured_rows"],
        "pair_count": report["pair_count"],
        "analysis": report["analysis"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
