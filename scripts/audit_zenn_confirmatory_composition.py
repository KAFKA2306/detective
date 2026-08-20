from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import statistics
from collections import Counter, defaultdict
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "reports" / "zenn_confirmatory_selection.json"
DEFAULT_OUTPUT = ROOT / "reports" / "zenn_confirmatory_composition.json"


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    weight = pos - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight


def summarize_lengths(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row["body_letters_count"]) for row in rows]
    q1 = percentile(values, 0.25)
    q3 = percentile(values, 0.75)
    return {
        "n": len(values),
        "mean": statistics.fmean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "std_population": statistics.pstdev(values) if len(values) > 1 else (0.0 if values else None),
        "q1": q1,
        "q3": q3,
        "iqr": (q3 - q1) if q1 is not None and q3 is not None else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def build_report(selection: dict[str, Any]) -> dict[str, Any]:
    rows = list(selection.get("selected", []))
    years = list(selection["protocol"]["years"])
    months = list(selection["protocol"]["months"])

    by_year: dict[int, list[dict[str, Any]]] = defaultdict(list)
    by_stratum: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    authors: Counter[str] = Counter()
    author_years: dict[str, set[int]] = defaultdict(set)

    for row in rows:
        published = dt.datetime.fromisoformat(row["published_at"].replace("Z", "+00:00"))
        year, month = published.year, published.month
        by_year[year].append(row)
        by_stratum[(year, month)].append(row)
        author = row["author_sha256"]
        authors[author] += 1
        author_years[author].add(year)

    strata = []
    for year in years:
        for month in months:
            stratum_rows = by_stratum[(year, month)]
            strata.append({
                "year": year,
                "month": month,
                "selected": len(stratum_rows),
                "unique_authors": len({row["author_sha256"] for row in stratum_rows}),
                "length": summarize_lengths(stratum_rows),
            })

    repeated_multi_year = {author: sorted(year_set) for author, year_set in author_years.items() if len(year_set) > 1}
    return {
        "schema_version": 1,
        "source": "reports/zenn_confirmatory_selection.json",
        "selected_rows": len(rows),
        "protocol": selection["protocol"],
        "length_all": summarize_lengths(rows),
        "length_by_year": {str(year): summarize_lengths(by_year[year]) for year in years},
        "author_concentration": {
            "unique_authors": len(authors),
            "max_articles_per_author": max(authors.values(), default=0),
            "authors_with_multiple_articles": sum(count > 1 for count in authors.values()),
            "authors_present_in_multiple_years": len(repeated_multi_year),
            "multi_year_author_years": repeated_multi_year,
        },
        "strata": strata,
        "limitations": [
            "This report audits selected-corpus composition only; it does not compute text features or detector outputs.",
            "Engagement and topic composition are not reported because they are not present in the current selection manifest.",
            "Author identifiers are SHA-256 hashes from the selection manifest; no author names are persisted here.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=pathlib.Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    selection = json.loads(args.input.read_text(encoding="utf-8"))
    report = build_report(selection)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.check:
        existing = args.output.read_text(encoding="utf-8")
        if existing != rendered:
            raise SystemExit("confirmatory composition report is stale; regenerate it")
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
