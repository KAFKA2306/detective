from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import urllib.parse
import xml.etree.ElementTree as ET
from collections import defaultdict

from zenn_public_page_probe import (
    BODY_LETTERS_PATTERNS,
    NS,
    PUBLISHED_PATTERNS,
    TYPE_PATTERNS,
    article_urls,
    fetch,
    first_match,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "corpus" / "zenn_confirmatory_candidates.jsonl"
SUMMARY = ROOT / "reports" / "zenn_confirmatory_collection.json"
STATUS = ROOT / "reports" / "zenn_sitemap_status.json"
YEARS = range(2022, 2027)
MONTHS = range(1, 8)
CANDIDATES_PER_STRATUM = 36


def parse_datetime(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed


def target(year: int, month: int) -> dt.datetime:
    return dt.datetime(year, month, 15, 12, tzinfo=dt.timezone(dt.timedelta(hours=9)))


def sitemap_candidates() -> dict[tuple[int, int], list[str]]:
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    if status.get("status") != "compatible":
        raise RuntimeError("official Zenn sitemap probe is not compatible")

    root = ET.fromstring(fetch(status["sitemap_index"], sitemap=True))
    sitemap_urls = [
        node.findtext("sm:loc", default="", namespaces=NS)
        for node in root.findall("sm:sitemap", NS)
    ]
    article_maps = [url for url in sitemap_urls if "/article" in urllib.parse.urlsplit(url).path]
    ranked: dict[tuple[int, int], list[tuple[float, str, str]]] = defaultdict(list)

    for sitemap_url in article_maps:
        doc = ET.fromstring(fetch(sitemap_url, sitemap=True))
        for node in doc.findall("sm:url", NS):
            loc = node.findtext("sm:loc", default="", namespaces=NS)
            lastmod = node.findtext("sm:lastmod", default="", namespaces=NS)
            if not loc or "/articles/" not in urllib.parse.urlsplit(loc).path or not lastmod:
                continue
            try:
                stamp = parse_datetime(lastmod)
            except ValueError:
                continue
            key = (stamp.year, stamp.month)
            if stamp.year in YEARS and stamp.month in MONTHS:
                distance = abs((stamp - target(*key)).total_seconds())
                ranked[key].append((distance, hashlib.sha256(loc.encode()).hexdigest(), loc))

    result: dict[tuple[int, int], list[str]] = {}
    for year in YEARS:
        for month in MONTHS:
            rows = sorted(ranked.get((year, month), []))
            result[(year, month)] = [url for _, _, url in rows[:CANDIDATES_PER_STRATUM]]
    return result


def public_metadata(url: str, fetched_at: str) -> dict[str, object] | None:
    source = fetch(url, sitemap=False).decode("utf-8", errors="replace")
    published_raw = first_match(PUBLISHED_PATTERNS, source)
    article_type = first_match(TYPE_PATTERNS, source)
    body_letters_raw = first_match(BODY_LETTERS_PATTERNS, source)
    path = urllib.parse.urlsplit(url).path.strip("/").split("/")
    author = path[0] if len(path) >= 3 and path[1] == "articles" else None
    if published_raw is None or article_type is None or body_letters_raw is None or author is None:
        return None
    try:
        published = parse_datetime(published_raw)
        body_letters_count = int(body_letters_raw)
    except (ValueError, TypeError):
        return None
    if published.year not in YEARS or published.month not in MONTHS:
        return None

    canonical_url = f"https://zenn.dev/{author}/articles/{path[2]}"
    stable = {
        "source_url": canonical_url,
        "published_at": published.isoformat(),
        "article_type": article_type.lower(),
        "body_letters_count": body_letters_count,
        "author_sha256": hashlib.sha256(author.encode()).hexdigest(),
    }
    return {
        "schema_version": 1,
        **stable,
        "fetched_at": fetched_at,
        "metadata_sha256": hashlib.sha256(
            json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "source": "Zenn official sitemap candidate discovery + public /articles/ page metadata",
        "sitemap_lastmod_used_as_publication_label": False,
        "raw_html_persisted": False,
        "article_body_persisted": False,
    }


def main() -> None:
    by_stratum = sitemap_candidates()
    candidate_urls = sorted({url for urls in by_stratum.values() for url in urls})
    fetched_at = dt.datetime.now(dt.UTC).isoformat()
    records: dict[str, dict[str, object]] = {}
    errors: dict[str, int] = defaultdict(int)

    for index, url in enumerate(candidate_urls, start=1):
        try:
            row = public_metadata(url, fetched_at)
            if row is not None:
                records[str(row["source_url"])] = row
        except Exception as exc:
            errors[type(exc).__name__] += 1
        print(f"[{index}/{len(candidate_urls)}] records={len(records)}")

    ordered = sorted(records.values(), key=lambda row: str(row["source_url"]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in ordered),
        encoding="utf-8",
    )

    actual: dict[str, int] = defaultdict(int)
    for row in ordered:
        published = parse_datetime(str(row["published_at"]))
        actual[f"{published.year}-{published.month:02d}"] += 1
    summary = {
        "schema_version": 1,
        "generated_at": fetched_at,
        "source": "https://zenn.dev/robots.txt -> official sitemap -> public /articles/ pages",
        "candidate_rule": "For each 2022-2026 Jan-Jul stratum, take up to 36 sitemap URLs whose lastmod is in that stratum, ranked by distance from month midpoint then SHA-256(URL). Revalidate publication stratum from the public article page.",
        "sitemap_lastmod_used_as_publication_label": False,
        "candidate_url_count": len(candidate_urls),
        "metadata_record_count": len(ordered),
        "errors": dict(sorted(errors.items())),
        "actual_publication_strata": dict(sorted(actual.items())),
        "raw_html_persisted": False,
        "article_body_persisted": False,
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
