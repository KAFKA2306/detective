from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "note_recommended_candidate_manifest.json"
USER_AGENT = "KAFKA2306-detective/0.1 (+https://github.com/KAFKA2306/detective)"
MAGAZINE_KEY = "m4bd0825e8f53"
YEARS = (2022, 2026)
MONTHS = tuple(range(1, 8))
REQUEST_INTERVAL_SECONDS = 0.35
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
ABSOLUTE_NOTE_RE = re.compile(r"https://note\.com/[A-Za-z0-9_-]+/n/[A-Za-z0-9_-]+")
INFO_NOTE_RE = re.compile(r"(?:https://note\.com)?/info/n/[A-Za-z0-9_-]+")

_last_request_at = 0.0


def allowed_note_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "note.com":
        return False
    if parsed.path.startswith("/api/") or parsed.path == "/search" or parsed.path.startswith("/search/"):
        return False
    return True


def throttled_fetch(url: str) -> str:
    global _last_request_at
    if not allowed_note_url(url):
        raise RuntimeError(f"refusing URL outside allowed public note paths: {url}")
    elapsed = time.monotonic() - _last_request_at
    if elapsed < REQUEST_INTERVAL_SECONDS:
        time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    _last_request_at = time.monotonic()
    return raw.decode("utf-8", errors="replace")


def normalized_embedded_source(source: str) -> str:
    return html.unescape(source).replace("\\u002F", "/").replace("\\u002f", "/").replace("\\/", "/")


def note_links(source: str, base_url: str) -> list[str]:
    links: set[str] = set()
    decoded = normalized_embedded_source(source)
    raw_links = list(HREF_RE.findall(decoded))
    raw_links.extend(ABSOLUTE_NOTE_RE.findall(decoded))
    raw_links.extend(INFO_NOTE_RE.findall(decoded))
    for raw_href in raw_links:
        url = urllib.parse.urljoin(base_url, raw_href)
        if allowed_note_url(url):
            parsed = urllib.parse.urlsplit(url)
            clean = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))
            links.add(clean)
    return sorted(links)


def summary_links(source: str, archive_url: str) -> list[str]:
    return [url for url in note_links(source, archive_url) if urllib.parse.urlsplit(url).path.startswith("/info/n/")]


def candidate_links(source: str, summary_url: str) -> list[str]:
    candidates: list[str] = []
    for url in note_links(source, summary_url):
        path = urllib.parse.urlsplit(url).path
        parts = [part for part in path.split("/") if part]
        if len(parts) == 3 and parts[1] == "n" and parts[0] != "info":
            candidates.append(url)
    return candidates


def archive_url(year: int, month: int) -> str:
    return f"https://note.com/info/m/{MAGAZINE_KEY}/archive/{year}-{month:02d}"


def main() -> None:
    rows: list[dict[str, object]] = []
    all_candidates: dict[int, set[str]] = {year: set() for year in YEARS}
    all_summaries: dict[int, set[str]] = {year: set() for year in YEARS}

    for year in YEARS:
        for month in MONTHS:
            source_url = archive_url(year, month)
            archive_source = throttled_fetch(source_url)
            summaries = summary_links(archive_source, source_url)
            candidates: set[str] = set()
            for summary_url in summaries:
                summary_source = throttled_fetch(summary_url)
                candidates.update(candidate_links(summary_source, summary_url))
            all_summaries[year].update(summaries)
            all_candidates[year].update(candidates)
            rows.append(
                {
                    "year": year,
                    "month": month,
                    "archive_url": source_url,
                    "summary_count": len(summaries),
                    "candidate_count": len(candidates),
                    "summary_urls": summaries,
                    "candidate_urls": sorted(candidates),
                }
            )
            print(f"{year}-{month:02d}: {len(summaries)} recommendation summaries, {len(candidates)} candidates")

    status = "compatible" if all(row["summary_count"] and row["candidate_count"] for row in rows) else "blocked"
    report = {
        "schema_version": 1,
        "status": status,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "source": "note公式『今月のおすすめ記事』monthly archive",
        "source_magazine_url": f"https://note.com/info/m/{MAGAZINE_KEY}/archive",
        "comparison_years": list(YEARS),
        "comparison_months": list(MONTHS),
        "candidate_definition": "public note article URLs linked from note公式 recommendation roundup posts in the same January-July archive window",
        "global_top_claim": False,
        "selection_stage": "bounded candidate discovery only; public reaction values are not collected or ranked by this script",
        "forbidden_paths_used": False,
        "raw_html_persisted": False,
        "by_month": rows,
        "year_totals": {
            str(year): {
                "summary_count": len(all_summaries[year]),
                "unique_candidate_count": len(all_candidates[year]),
                "candidate_set_sha256": hashlib.sha256("\n".join(sorted(all_candidates[year])).encode("utf-8")).hexdigest(),
            }
            for year in YEARS
        },
        "caveats": [
            "The official recommendation cadence changed over time, so candidate-set size and editorial selection intensity must be audited before outcome comparison.",
            "This is not an all-note ranking and must not be described as global top articles.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if status != "compatible":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
