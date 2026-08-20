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
    fetch,
    first_match,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "corpus" / "zenn_confirmatory_candidates.jsonl"
SUMMARY = ROOT / "reports" / "zenn_confirmatory_collection.json"
STATUS = ROOT / "reports" / "zenn_sitemap_status.json"
YEARS = range(2022, 2027)
MONTHS = range(1, 8)
CANDIDATES_PER_SITEMAP = 144


def parse_datetime(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed


def sitemap_candidates() -> tuple[list[str], dict[str, int]]:
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    if status.get("status") != "compatible":
        raise RuntimeError("official Zenn sitemap probe is not compatible")

    root = ET.fromstring(fetch(status["sitemap_index"], sitemap=True))
    sitemap_urls = [
        node.findtext("sm:loc", default="", namespaces=NS)
        for node in root.findall("sm:sitemap", NS)
    ]
    article_maps = [url for url in sitemap_urls if "/article" in urllib.parse.urlsplit(url).path]
    selected: set[str] = set()
    counts: dict[str, int] = {}

    for sitemap_url in sorted(article_maps):
        doc = ET.fromstring(fetch(sitemap_url, sitemap=True))
        urls = {
            node.findtext("sm:loc", default="", namespaces=NS)
            for node in doc.findall("sm:url", NS)
        }
        article_urls = sorted(
            (
                url
                for url in urls
                if url and "/articles/" in urllib.parse.urlsplit(url).path
            ),
            key=lambda url: (hashlib.sha256(url.encode()).hexdigest(), url),
        )
        sample = article_urls[:CANDIDATES_PER_SITEMAP]
        selected.update(sample)
        counts[sitemap_url] = len(sample)

    return sorted(selected), counts


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
    candidate_urls, sitemap_sample_counts = sitemap_candidates()
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
        "candidate_rule": (
            "From every official article sitemap, take a deterministic SHA-256(URL)-ordered sample "
            f"of up to {CANDIDATES_PER_SITEMAP} public article URLs. Do not use sitemap lastmod for "
            "candidate strata or publication labels; derive publication strata only from each public article page."
        ),
        "sitemap_lastmod_used_for_candidate_selection": False,
        "sitemap_lastmod_used_as_publication_label": False,
        "article_sitemap_count": len(sitemap_sample_counts),
        "candidates_per_sitemap": CANDIDATES_PER_SITEMAP,
        "sitemap_sample_counts": dict(sorted(sitemap_sample_counts.items())),
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
