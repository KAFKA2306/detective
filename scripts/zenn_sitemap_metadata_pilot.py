from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import pathlib
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "reports" / "zenn_article_sitemap_inventory.json"
OUTPUT_JSONL = ROOT / "corpus" / "zenn_august_sitemap_pilot.jsonl"
OUTPUT_SUMMARY = ROOT / "reports" / "zenn_august_sitemap_pilot_summary.json"
USER_AGENT = "KAFKA2306-detective/0.1 (+https://github.com/KAFKA2306/detective)"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

YEARS = tuple(range(2022, 2027))
SAMPLES_PER_YEAR = 12
TARGET_MONTH = 8
TARGET_DAY = 1
TARGET_HOUR_JST = 12
MIN_BODY_LETTERS_COUNT = 1500
PUBLISHED_WINDOW_DAYS = 7
LASTMOD_CANDIDATE_WINDOW_DAYS = 45
MAX_DETAIL_REQUESTS_PER_YEAR = 80
REQUEST_INTERVAL_SECONDS = 0.40

_last_request_at = 0.0


def throttled_fetch(url: str, *, accept: str) -> bytes:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < REQUEST_INTERVAL_SECONDS:
        time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    _last_request_at = time.monotonic()
    return raw


def fetch_xml(url: str) -> bytes:
    raw = throttled_fetch(url, accept="application/gzip,application/xml,text/xml;q=0.9,*/*;q=0.1")
    return gzip.decompress(raw) if url.endswith(".gz") else raw


def parse_datetime(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value)


def target_for_year(year: int) -> dt.datetime:
    return dt.datetime(year, TARGET_MONTH, TARGET_DAY, TARGET_HOUR_JST, tzinfo=dt.timezone(dt.timedelta(hours=9)))


def load_sitemap_candidates(sitemaps: list[str]) -> dict[int, list[tuple[float, str, str]]]:
    result: dict[int, list[tuple[float, str, str]]] = {year: [] for year in YEARS}
    windows = {year: target_for_year(year) for year in YEARS}
    max_seconds = LASTMOD_CANDIDATE_WINDOW_DAYS * 86400
    for sitemap in sitemaps:
        root = ET.fromstring(fetch_xml(sitemap))
        for node in root.findall("sm:url", NS):
            loc = node.findtext("sm:loc", default="", namespaces=NS)
            lastmod = node.findtext("sm:lastmod", default="", namespaces=NS)
            if not loc or not lastmod:
                continue
            stamp = parse_datetime(lastmod)
            for year, target in windows.items():
                distance = abs((stamp - target).total_seconds())
                if distance <= max_seconds:
                    result[year].append((distance, loc, lastmod))
    for year in YEARS:
        result[year].sort(key=lambda row: (row[0], hashlib.sha256(row[1].encode()).hexdigest()))
    return result


def article_slug(url: str) -> str:
    path = urllib.parse.urlsplit(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1]
    if not slug:
        raise RuntimeError(f"cannot derive slug from {url}")
    return slug


def fetch_article_detail(url: str) -> dict:
    slug = article_slug(url)
    endpoint = f"https://zenn.dev/api/articles/{urllib.parse.quote(slug)}"
    payload = json.loads(throttled_fetch(endpoint, accept="application/json").decode("utf-8"))
    article = payload.get("article") if isinstance(payload, dict) else None
    if not isinstance(article, dict):
        raise RuntimeError(f"detail endpoint returned no article for {url}")
    return article


def author_hash(article: dict) -> str | None:
    user = article.get("user")
    if not isinstance(user, dict):
        return None
    identifier = user.get("username") or user.get("id")
    return hashlib.sha256(str(identifier).encode("utf-8")).hexdigest() if identifier is not None else None


def build_record(source_url: str, lastmod: str, article: dict, year: int, target: dt.datetime) -> dict:
    path = urllib.parse.urlsplit(source_url).path
    stable = {
        "source_url": f"https://zenn.dev{path}",
        "published_at": article.get("published_at"),
        "article_type": article.get("article_type"),
        "liked_count": article.get("liked_count"),
        "body_letters_count": article.get("body_letters_count"),
        "author_sha256": author_hash(article),
    }
    digest = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    published = parse_datetime(str(article["published_at"]))
    return {
        "schema_version": 2,
        "source": "official-sitemap+undocumented-detail-metadata",
        "source_url": stable["source_url"],
        "year": year,
        "cohort": "august-sitemap-pilot-v2",
        "target_at": target.isoformat(),
        "published_at": stable["published_at"],
        "distance_from_target_seconds": abs((published - target).total_seconds()),
        "sitemap_lastmod": lastmod,
        "article_type": stable["article_type"],
        "liked_count": stable["liked_count"],
        "body_letters_count": stable["body_letters_count"],
        "author_sha256": stable["author_sha256"],
        "metadata_sha256": digest,
    }


def select_year(year: int, candidates: list[tuple[float, str, str]]) -> tuple[list[dict], int]:
    target = target_for_year(year)
    published_limit = PUBLISHED_WINDOW_DAYS * 86400
    selected: list[dict] = []
    requests = 0
    seen_paths: set[str] = set()
    for _, url, lastmod in candidates:
        if requests >= MAX_DETAIL_REQUESTS_PER_YEAR or len(selected) >= SAMPLES_PER_YEAR:
            break
        path = urllib.parse.urlsplit(url).path
        if path in seen_paths or "/articles/" not in path:
            continue
        seen_paths.add(path)
        try:
            article = fetch_article_detail(url)
        except Exception as exc:
            print(f"detail skip {url}: {type(exc).__name__}: {exc}")
            requests += 1
            continue
        requests += 1

        published_at = article.get("published_at")
        body_letters_count = article.get("body_letters_count")
        if not isinstance(published_at, str) or article.get("article_type") != "tech":
            continue
        if not isinstance(body_letters_count, int) or body_letters_count < MIN_BODY_LETTERS_COUNT:
            continue
        published = parse_datetime(published_at)
        if published.year != year or abs((published - target).total_seconds()) > published_limit:
            continue
        detail_path = article.get("path")
        if isinstance(detail_path, str) and detail_path != path:
            continue
        selected.append(build_record(url, lastmod, article, year, target))

    if len(selected) < SAMPLES_PER_YEAR:
        raise RuntimeError(
            f"{year}: selected {len(selected)}/{SAMPLES_PER_YEAR} after {requests} detail requests "
            f"from {len(candidates)} sitemap candidates"
        )
    selected.sort(key=lambda row: (row["distance_from_target_seconds"], row["metadata_sha256"]))
    return selected[:SAMPLES_PER_YEAR], requests


def median(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def main() -> None:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    if inventory.get("status") != "compatible":
        raise SystemExit("official article sitemap inventory is not compatible")
    sitemaps = [row["sitemap"] for row in inventory.get("sitemaps", []) if isinstance(row, dict) and row.get("sitemap")]
    candidates = load_sitemap_candidates(sitemaps)

    all_records: list[dict] = []
    request_counts: dict[str, int] = {}
    candidate_counts: dict[str, int] = {}
    for year in YEARS:
        candidate_counts[str(year)] = len(candidates[year])
        records, requests = select_year(year, candidates[year])
        all_records.extend(records)
        request_counts[str(year)] = requests
        print(f"{year}: {len(records)} selected from {len(candidates[year])} candidates using {requests} detail requests")

    all_records.sort(key=lambda row: (row["year"], row["published_at"], row["source_url"]))
    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSONL.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in all_records), encoding="utf-8")

    years: dict[str, dict] = {}
    for year in YEARS:
        rows = [row for row in all_records if row["year"] == year]
        years[str(year)] = {
            "count": len(rows),
            "published_at_min": min(row["published_at"] for row in rows),
            "published_at_max": max(row["published_at"] for row in rows),
            "unique_author_hashes": len({row["author_sha256"] for row in rows if row["author_sha256"]}),
            "liked_count_median": median([int(row["liked_count"]) for row in rows]),
            "body_letters_count_median": median([int(row["body_letters_count"]) for row in rows]),
            "sitemap_candidate_count": candidate_counts[str(year)],
            "detail_request_count": request_counts[str(year)],
        }

    summary = {
        "schema_version": 2,
        "status": "pilot_ready",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "source": "official-sitemap+undocumented-detail-metadata",
        "selection": {
            "cohort": "august-sitemap-pilot-v2",
            "target_month_day": f"{TARGET_MONTH:02d}-{TARGET_DAY:02d}",
            "target_hour_jst": TARGET_HOUR_JST,
            "samples_per_year": SAMPLES_PER_YEAR,
            "article_type": "tech",
            "min_body_letters_count": MIN_BODY_LETTERS_COUNT,
            "published_window_days": PUBLISHED_WINDOW_DAYS,
            "lastmod_candidate_window_days": LASTMOD_CANDIDATE_WINDOW_DAYS,
            "lastmod_is_label": False,
            "purpose": "same-season fixed-length-eligible historical pilot; not the final yearly baseline",
        },
        "years": years,
    }
    OUTPUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
