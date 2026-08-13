from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_STATUS = ROOT / "reports" / "zenn_source_status.json"
OUTPUT_JSONL = ROOT / "corpus" / "zenn_august_pilot.jsonl"
OUTPUT_SUMMARY = ROOT / "reports" / "zenn_august_pilot_summary.json"

API_BASE = "https://zenn.dev/api/articles"
USER_AGENT = "KAFKA2306-detective/0.1 (+https://github.com/KAFKA2306/detective)"
YEARS = tuple(range(2022, 2027))
TARGET_MONTH = 8
TARGET_DAY = 1
SAMPLES_PER_YEAR = 12
PAGE_COUNT = 48
MAX_DISTANCE_DAYS = 7
REQUEST_INTERVAL_SECONDS = 0.35

_page_cache: dict[int, dict] = {}
_last_request_at = 0.0


def parse_datetime(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value)


def fetch_page(page: int) -> dict:
    global _last_request_at
    if page in _page_cache:
        return _page_cache[page]

    elapsed = time.monotonic() - _last_request_at
    if elapsed < REQUEST_INTERVAL_SECONDS:
        time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)

    query = urllib.parse.urlencode({"order": "latest", "count": PAGE_COUNT, "page": page})
    request = urllib.request.Request(
        f"{API_BASE}?{query}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        # Zenn returns HTTP 404 when a page index is beyond the current
        # pagination range. During exponential search this is a valid upper
        # boundary, not a reason to weaken the cohort selection criteria.
        if exc.code == 404 and page > 1:
            payload = {"articles": [], "next_page": None, "out_of_range": True}
        else:
            raise
    _last_request_at = time.monotonic()
    if not isinstance(payload, dict):
        raise RuntimeError(f"page {page}: non-object response")
    articles = payload.get("articles")
    if articles is not None and not isinstance(articles, list):
        raise RuntimeError(f"page {page}: articles is not a list")
    _page_cache[page] = payload
    return payload


def dated_articles(page: int) -> list[tuple[dt.datetime, dict]]:
    rows: list[tuple[dt.datetime, dict]] = []
    for article in fetch_page(page).get("articles", []):
        if not isinstance(article, dict):
            continue
        value = article.get("published_at")
        if isinstance(value, str):
            rows.append((parse_datetime(value), article))
    rows.sort(key=lambda item: item[0], reverse=True)
    return rows


def locate_page(target: dt.datetime) -> int:
    """Locate a page near target using exponential search followed by binary search."""
    first = dated_articles(1)
    if not first:
        raise RuntimeError("page 1 is empty")
    if target >= first[0][0]:
        return 1

    low = 1
    high = 2
    for _ in range(24):
        rows = dated_articles(high)
        if not rows:
            break
        newest, oldest = rows[0][0], rows[-1][0]
        if oldest <= target <= newest:
            return high
        if newest < target:
            break
        low = high
        high *= 2
    else:
        raise RuntimeError(f"failed to bracket target {target.isoformat()}")

    while low + 1 < high:
        mid = (low + high) // 2
        rows = dated_articles(mid)
        if not rows:
            high = mid
            continue
        newest, oldest = rows[0][0], rows[-1][0]
        if oldest <= target <= newest:
            return mid
        if oldest > target:
            low = mid
        else:
            high = mid

    candidates: list[tuple[float, int]] = []
    for page in {low, high}:
        rows = dated_articles(page)
        if rows:
            distance = min(abs((stamp - target).total_seconds()) for stamp, _ in rows)
            candidates.append((distance, page))
    if not candidates:
        raise RuntimeError(f"no page near target {target.isoformat()}")
    candidates.sort()
    return candidates[0][1]


def public_author_hash(article: dict) -> str | None:
    user = article.get("user")
    if not isinstance(user, dict):
        return None
    identifier = user.get("username") or user.get("id")
    if identifier is None:
        return None
    return hashlib.sha256(str(identifier).encode("utf-8")).hexdigest()


def canonical_record(article: dict, year: int, target: dt.datetime) -> dict:
    path = article.get("path")
    if not isinstance(path, str) or not path.startswith("/"):
        raise RuntimeError("article path is missing")
    published_at = article.get("published_at")
    if not isinstance(published_at, str):
        raise RuntimeError("published_at is missing")

    stable = {
        "id": article.get("id"),
        "slug": article.get("slug"),
        "path": path,
        "published_at": published_at,
        "liked_count": article.get("liked_count"),
        "body_letters_count": article.get("body_letters_count"),
        "article_type": article.get("article_type"),
        "author_sha256": public_author_hash(article),
    }
    stable_bytes = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    published = parse_datetime(published_at)
    return {
        "schema_version": 1,
        "source": "zenn-undocumented-articles-json",
        "source_url": f"https://zenn.dev{path}",
        "year": year,
        "cohort": "august-pilot",
        "target_at": target.isoformat(),
        "published_at": published_at,
        "distance_from_target_seconds": abs((published - target).total_seconds()),
        "article_type": article.get("article_type"),
        "liked_count": article.get("liked_count"),
        "body_letters_count": article.get("body_letters_count"),
        "author_sha256": stable["author_sha256"],
        "metadata_sha256": hashlib.sha256(stable_bytes).hexdigest(),
    }


def select_year(year: int) -> tuple[list[dict], int]:
    jst = dt.timezone(dt.timedelta(hours=9))
    target = dt.datetime(year, TARGET_MONTH, TARGET_DAY, 12, 0, tzinfo=jst)
    center_page = locate_page(target)

    pool: dict[object, tuple[dt.datetime, dict]] = {}
    for page in range(max(1, center_page - 2), center_page + 3):
        for stamp, article in dated_articles(page):
            if stamp.year != year or article.get("article_type") != "tech":
                continue
            key = article.get("id") or article.get("path")
            pool[key] = (stamp, article)

    ranked = sorted(pool.values(), key=lambda item: (abs((item[0] - target).total_seconds()), str(item[1].get("id"))))
    max_distance = MAX_DISTANCE_DAYS * 86400
    ranked = [item for item in ranked if abs((item[0] - target).total_seconds()) <= max_distance]
    if len(ranked) < SAMPLES_PER_YEAR:
        raise RuntimeError(
            f"{year}: only {len(ranked)} tech articles within ±{MAX_DISTANCE_DAYS} days of target"
        )
    return [canonical_record(article, year, target) for _, article in ranked[:SAMPLES_PER_YEAR]], center_page


def main() -> None:
    source_status = json.loads(SOURCE_STATUS.read_text(encoding="utf-8"))
    if source_status.get("status") != "compatible":
        raise SystemExit("Zenn source probe is not compatible; refusing to collect metadata")

    generated_at = dt.datetime.now(dt.UTC).isoformat()
    all_records: list[dict] = []
    pages: dict[str, int] = {}
    for year in YEARS:
        records, page = select_year(year)
        all_records.extend(records)
        pages[str(year)] = page
        print(f"{year}: selected {len(records)} records near page {page}")

    all_records.sort(key=lambda row: (row["year"], row["published_at"], row["source_url"]))
    OUTPUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSONL.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in all_records),
        encoding="utf-8",
    )

    year_rows: dict[str, dict] = {}
    for year in YEARS:
        rows = [row for row in all_records if row["year"] == year]
        year_rows[str(year)] = {
            "count": len(rows),
            "published_at_min": min(row["published_at"] for row in rows),
            "published_at_max": max(row["published_at"] for row in rows),
            "unique_author_hashes": len({row["author_sha256"] for row in rows if row["author_sha256"]}),
            "liked_count_median": sorted(row["liked_count"] for row in rows)[len(rows) // 2],
            "body_letters_count_median": sorted(row["body_letters_count"] for row in rows)[len(rows) // 2],
            "located_page": pages[str(year)],
        }

    summary = {
        "schema_version": 1,
        "status": "pilot_ready",
        "generated_at": generated_at,
        "source": "zenn-undocumented-articles-json",
        "source_documented_by_zenn": False,
        "selection": {
            "cohort": "august-pilot",
            "years": list(YEARS),
            "target_month_day": f"{TARGET_MONTH:02d}-{TARGET_DAY:02d}",
            "target_hour_jst": 12,
            "samples_per_year": SAMPLES_PER_YEAR,
            "article_type": "tech",
            "max_distance_days": MAX_DISTANCE_DAYS,
            "purpose": "same-season metadata pilot; not the final yearly baseline",
        },
        "request_count": len(_page_cache),
        "years": year_rows,
    }
    OUTPUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
