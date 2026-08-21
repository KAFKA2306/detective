from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import pathlib
import re

import note_public_page_probe as public_page

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports" / "note_recommended_candidate_manifest.json"
OUTPUT = ROOT / "reports" / "note_recommended_candidate_metadata.json"
TARGET_YEARS = (2022, 2026)
TARGET_MONTHS = frozenset(range(1, 8))


def candidate_years(manifest: dict[str, object]) -> dict[str, set[int]]:
    result: dict[str, set[int]] = collections.defaultdict(set)
    for row in manifest.get("by_month", []):
        if not isinstance(row, dict):
            continue
        year = row.get("year")
        urls = row.get("candidate_urls", [])
        if year not in TARGET_YEARS or not isinstance(urls, list):
            continue
        for url in urls:
            if isinstance(url, str):
                result[url].add(int(year))
    return dict(result)


def parse_publication(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    match = re.match(r"^(20\d{2})-(\d{2})", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def is_same_window(publication: tuple[int, int] | None, recommendation_years: set[int]) -> bool:
    if publication is None:
        return False
    year, month = publication
    return year in recommendation_years and month in TARGET_MONTHS


def main() -> None:
    manifest = json.loads(SOURCE.read_text(encoding="utf-8"))
    if manifest.get("status") != "compatible":
        raise RuntimeError("note recommendation candidate manifest is not compatible")

    url_years = candidate_years(manifest)
    records: list[dict[str, object]] = []
    errors: collections.Counter[str] = collections.Counter()
    by_year = {
        year: {
            "candidate_urls": 0,
            "published_in_same_jan_jul_window": 0,
            "reaction_count_observed_in_same_window": 0,
            "reaction_count_missing_in_same_window": 0,
        }
        for year in TARGET_YEARS
    }
    for years in url_years.values():
        for year in years:
            by_year[year]["candidate_urls"] += 1

    published_success = 0
    reaction_success = 0
    same_window_count = 0
    cross_year_candidates = 0

    for index, url in enumerate(sorted(url_years), start=1):
        recommendation_years = url_years[url]
        if len(recommendation_years) > 1:
            cross_year_candidates += 1
        fetched_at = dt.datetime.now(dt.UTC).isoformat()
        record: dict[str, object] = {
            "source_url": url,
            "source_url_sha256": hashlib.sha256(url.encode("utf-8")).hexdigest(),
            "recommendation_years": sorted(recommendation_years),
            "fetched_at": fetched_at,
            "published_at": None,
            "public_reaction_count": None,
            "page_sha256": None,
            "published_in_same_jan_jul_window": False,
            "error": None,
        }
        try:
            raw = public_page.throttled_fetch(url)
            source = raw.decode("utf-8", errors="replace")
            published = public_page.first_match(public_page.PUBLISHED_PATTERNS, source)
            reaction_raw = public_page.public_reaction_count(source)
            publication = parse_publication(published)
            same_window = is_same_window(publication, recommendation_years)

            record["page_sha256"] = hashlib.sha256(raw).hexdigest()
            record["published_at"] = published
            record["public_reaction_count"] = int(reaction_raw) if reaction_raw is not None else None
            record["published_in_same_jan_jul_window"] = same_window

            if published is not None:
                published_success += 1
            if reaction_raw is not None:
                reaction_success += 1
            if same_window and publication is not None:
                same_window_count += 1
                year, _ = publication
                by_year[year]["published_in_same_jan_jul_window"] += 1
                if reaction_raw is None:
                    by_year[year]["reaction_count_missing_in_same_window"] += 1
                else:
                    by_year[year]["reaction_count_observed_in_same_window"] += 1
            print(
                f"[{index}/{len(url_years)}] published={published is not None} "
                f"reaction={reaction_raw is not None} same_window={same_window} {url}"
            )
        except Exception as exc:
            errors[type(exc).__name__] += 1
            record["error"] = type(exc).__name__
            print(f"[{index}/{len(url_years)}] ERROR {type(exc).__name__}: {exc} {url}")
        records.append(record)

    report = {
        "schema_version": 1,
        "status": "compatible" if not errors and published_success == len(url_years) else "blocked",
        "checked_at": dt.datetime.now(dt.UTC).isoformat(),
        "source_candidate_manifest_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "candidate_definition": manifest.get("candidate_definition"),
        "global_top_claim": False,
        "comparison_years": list(TARGET_YEARS),
        "comparison_months": sorted(TARGET_MONTHS),
        "candidate_url_count": len(url_years),
        "cross_year_candidate_url_count": cross_year_candidates,
        "published_at_extracted": published_success,
        "public_reaction_count_extracted": reaction_success,
        "published_in_same_jan_jul_window": same_window_count,
        "errors": dict(sorted(errors.items())),
        "by_year": {str(year): values for year, values in by_year.items()},
        "records": records,
        "collection_paths": ["note official recommendation archive pages (upstream manifest)", "/*/n/*"],
        "forbidden_paths_used": False,
        "raw_html_persisted": False,
        "selection_stage": "metadata audit only; no high-engagement threshold or ranking is selected by this script",
        "caveats": [
            "A recommendation-page year is not treated as an article publication year; eligibility requires the public article published_at value to fall in the same January-July window.",
            "Missing public reaction counts remain missing and are not imputed as zero.",
            "The official recommendation cadence differs by year, so candidate-set size is not an engagement outcome.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "compatible":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
