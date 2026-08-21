from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import pathlib
from urllib.parse import urlparse

TARGET_YEARS = (2022, 2026)
TARGET_MONTHS = tuple(range(1, 8))
UPPER_QUARTILE_FRACTION = 0.25


def publication_year_month(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str) or len(value) < 7:
        return None
    try:
        return int(value[:4]), int(value[5:7])
    except ValueError:
        return None


def author_sha256(source_url: str) -> str:
    parts = [part for part in urlparse(source_url).path.split("/") if part]
    if len(parts) < 3 or parts[1] != "n":
        raise ValueError(f"unexpected note article URL: {source_url}")
    return hashlib.sha256(parts[0].encode("utf-8")).hexdigest()


def eligible_records(report: dict[str, object]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in report.get("records", []):
        if not isinstance(row, dict):
            continue
        ym = publication_year_month(row.get("published_at"))
        reaction = row.get("public_reaction_count")
        required_strings = ("source_url", "source_url_sha256", "page_sha256", "fetched_at")
        if (
            row.get("published_in_same_jan_jul_window") is True
            and ym is not None
            and ym[0] in TARGET_YEARS
            and ym[1] in TARGET_MONTHS
            and isinstance(reaction, int)
            and reaction >= 0
            and all(isinstance(row.get(key), str) for key in required_strings)
        ):
            result.append(row)
    return result


def select(report: dict[str, object], source_sha256: str) -> dict[str, object]:
    eligible = eligible_records(report)
    groups: dict[tuple[int, int], list[dict[str, object]]] = collections.defaultdict(list)
    for row in eligible:
        ym = publication_year_month(row["published_at"])
        assert ym is not None
        groups[ym].append(row)

    selected: list[dict[str, object]] = []
    strata: list[dict[str, object]] = []
    for month in TARGET_MONTHS:
        counts = {year: len(groups[(year, month)]) for year in TARGET_YEARS}
        quartile_counts = {
            year: math.ceil(counts[year] * UPPER_QUARTILE_FRACTION) for year in TARGET_YEARS
        }
        matched_count = min(quartile_counts.values())
        if matched_count < 1:
            raise RuntimeError(f"month {month} has no matched upper-quartile sample")

        chosen_by_year: dict[int, list[dict[str, object]]] = {}
        for year in TARGET_YEARS:
            ranked = sorted(
                groups[(year, month)],
                key=lambda row: (-int(row["public_reaction_count"]), str(row["source_url_sha256"])),
            )
            chosen = ranked[:matched_count]
            chosen_by_year[year] = chosen
            for rank, row in enumerate(chosen, start=1):
                selected.append(
                    {
                        "year": year,
                        "month": month,
                        "rank_within_year_month": rank,
                        "source_url": row["source_url"],
                        "source_url_sha256": row["source_url_sha256"],
                        "author_sha256": author_sha256(str(row["source_url"])),
                        "published_at": row["published_at"],
                        "fetched_at": row["fetched_at"],
                        "page_sha256": row["page_sha256"],
                        "public_reaction_count": row["public_reaction_count"],
                    }
                )
        strata.append(
            {
                "month": month,
                "eligible_count": {str(year): counts[year] for year in TARGET_YEARS},
                "upper_quartile_count": {str(year): quartile_counts[year] for year in TARGET_YEARS},
                "matched_selected_count_per_year": matched_count,
                "selected_reaction_range": {
                    str(year): {
                        "min": min(int(row["public_reaction_count"]) for row in chosen_by_year[year]),
                        "max": max(int(row["public_reaction_count"]) for row in chosen_by_year[year]),
                    }
                    for year in TARGET_YEARS
                },
            }
        )

    by_year = collections.Counter(int(row["year"]) for row in selected)
    author_counts = collections.Counter(
        (int(row["year"]), str(row["author_sha256"])) for row in selected
    )
    return {
        "schema_version": 1,
        "status": "fixed_before_text_feature_measurement",
        "source_metadata_sha256": source_sha256,
        "source_metadata_checked_at": report.get("checked_at"),
        "comparison_years": list(TARGET_YEARS),
        "comparison_months": list(TARGET_MONTHS),
        "candidate_definition": report.get("candidate_definition"),
        "global_top_claim": False,
        "selection_rule": (
            "Within each publication year-month stratum, rank eligible official-recommendation "
            "candidates by public_reaction_count descending with source_url_sha256 ascending as "
            "the deterministic tie-breaker. Define the upper-quartile count as ceil(n*0.25) in "
            "each year. Select the same count in both years for that month, equal to the smaller "
            "of the two upper-quartile counts. No text feature is used for selection."
        ),
        "eligible_record_count": len(eligible),
        "selected_record_count": len(selected),
        "selected_by_year": {str(year): by_year[year] for year in TARGET_YEARS},
        "max_selected_articles_per_author_within_year": max(author_counts.values(), default=0),
        "strata": strata,
        "records": selected,
        "raw_html_persisted": False,
        "text_features_used_for_selection": False,
        "caveats": [
            "The source pool is limited to articles recommended by note公式『今月のおすすめ記事』; it is not a population-wide or global-top sample.",
            "Recommendation cadence differs between 2022 and 2026. Matching selected counts within each publication month controls sample count and season but does not remove editorial-selection differences.",
            "Public reaction counts are observations at the metadata audit fetch time, not reactions accrued within a fixed post-publication interval.",
            "The upper-quartile rule is fixed before entropy, NCD, or detector measurement; text features are not consulted.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    source_bytes = args.input.read_bytes()
    report = json.loads(source_bytes)
    if report.get("status") not in {"compatible", "compatible_with_unavailable_records"}:
        raise RuntimeError("note candidate metadata is not compatible")
    output = select(report, hashlib.sha256(source_bytes).hexdigest())
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
