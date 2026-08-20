from __future__ import annotations

import collections
import datetime as dt
import gzip
import hashlib
import html
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports" / "note_sitemap_status.json"
OUTPUT = ROOT / "reports" / "note_public_page_status.json"
USER_AGENT = "KAFKA2306-detective/0.1 (+https://github.com/KAFKA2306/detective)"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
SAMPLE_SIZE = 60
REQUEST_INTERVAL_SECONDS = 0.35

_last_request_at = 0.0

PUBLISHED_PATTERNS = [
    re.compile(r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)', re.I),
    re.compile(r'"datePublished"\s*:\s*"([^"]+)"'),
    re.compile(r'"publishedAt"\s*:\s*"([^"]+)"'),
    re.compile(r'"publishAt"\s*:\s*"([^"]+)"'),
]
LIKE_PATTERNS = [
    re.compile(r'"likeCount"\s*:\s*(\d+)'),
    re.compile(r'"likesCount"\s*:\s*(\d+)'),
    re.compile(r'"like_count"\s*:\s*(\d+)'),
]


class ReactionButtonParser(HTMLParser):
    """Extract conservative numeric candidates from server-rendered buttons."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_button = False
        self._button_text: list[str] = []
        self._button_is_reaction = False
        self.reaction_counts: list[int] = []
        self.numeric_button_counts: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "button" or self._in_button:
            return
        self._in_button = True
        self._button_text = []
        values = " ".join(value or "" for _, value in attrs).lower()
        self._button_is_reaction = "スキ" in values or "like" in values or "reaction" in values

    def handle_data(self, data: str) -> None:
        if self._in_button:
            self._button_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "button" or not self._in_button:
            return
        text = "".join(self._button_text).strip().replace(",", "")
        if text.isdigit():
            value = int(text)
            self.numeric_button_counts.append(value)
            if self._button_is_reaction:
                self.reaction_counts.append(value)
        self._in_button = False
        self._button_text = []
        self._button_is_reaction = False


def throttled_fetch(url: str, *, sitemap: bool = False) -> bytes:
    global _last_request_at
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "note.com":
        raise RuntimeError(f"refusing non-note URL: {url}")
    if parsed.path.startswith("/api/") or parsed.path == "/search" or parsed.path.startswith("/search/"):
        raise RuntimeError(f"refusing robots-disallowed path: {parsed.path}")
    if sitemap and not parsed.path.startswith("/sitemaps/"):
        raise RuntimeError(f"expected sitemap path: {url}")
    if not sitemap and "/n/" not in parsed.path:
        raise RuntimeError(f"expected public note article path: {url}")

    elapsed = time.monotonic() - _last_request_at
    if elapsed < REQUEST_INTERVAL_SECONDS:
        time.sleep(REQUEST_INTERVAL_SECONDS - elapsed)
    accept = "application/gzip,application/xml,text/xml;q=0.9,*/*;q=0.1" if sitemap else "text/html,application/xhtml+xml"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    _last_request_at = time.monotonic()
    if sitemap and (url.endswith(".gz") or raw[:2] == b"\x1f\x8b"):
        return gzip.decompress(raw)
    return raw


def all_article_urls() -> list[str]:
    status = json.loads(SOURCE.read_text(encoding="utf-8"))
    if status.get("status") != "compatible":
        raise RuntimeError("note source probe is not compatible")
    children = status.get("sitemap", {}).get("child_sitemaps_sample", [])
    sitemaps = [
        url for url in children
        if isinstance(url, str) and pathlib.PurePosixPath(urllib.parse.urlsplit(url).path).name.startswith("notes")
    ]
    urls: list[str] = []
    for sitemap_url in sitemaps:
        root = ET.fromstring(throttled_fetch(sitemap_url, sitemap=True))
        for node in root.findall("sm:url", NS):
            loc = node.findtext("sm:loc", default="", namespaces=NS)
            if loc and "/n/" in urllib.parse.urlsplit(loc).path:
                urls.append(loc)
    return urls


def deterministic_sample(urls: list[str]) -> list[str]:
    ranked = sorted((hashlib.sha256(url.encode("utf-8")).hexdigest(), url) for url in set(urls))
    return [url for _, url in ranked[:SAMPLE_SIZE]]


def first_match(patterns: list[re.Pattern[str]], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return html.unescape(match.group(1))
    return None


def public_reaction_count(source: str) -> str | None:
    structured = first_match(LIKE_PATTERNS, source)
    if structured is not None:
        return structured

    parser = ReactionButtonParser()
    parser.feed(source)

    labeled = set(parser.reaction_counts)
    if len(labeled) == 1:
        return str(next(iter(labeled)))

    # Public note pages currently render the reaction count as button text. Only
    # accept the unlabeled fallback when the page exposes one unique numeric
    # button value, so unrelated button numbers cannot silently become likes.
    numeric = set(parser.numeric_button_counts)
    if len(numeric) == 1:
        return str(next(iter(numeric)))
    return None


def main() -> None:
    urls = all_article_urls()
    sample = deterministic_sample(urls)
    if len(sample) != SAMPLE_SIZE:
        raise RuntimeError(f"expected {SAMPLE_SIZE} sample URLs, got {len(sample)}")

    published_success = 0
    like_success = 0
    years: collections.Counter[int] = collections.Counter()
    likes_by_year: dict[int, list[int]] = collections.defaultdict(list)
    errors: collections.Counter[str] = collections.Counter()

    for index, url in enumerate(sample, start=1):
        try:
            source = throttled_fetch(url).decode("utf-8", errors="replace")
            published = first_match(PUBLISHED_PATTERNS, source)
            like_raw = public_reaction_count(source)
            if published:
                published_success += 1
                year_match = re.search(r"(20\d{2})", published)
                if year_match:
                    year = int(year_match.group(1))
                    years[year] += 1
                    if like_raw is not None:
                        likes_by_year[year].append(int(like_raw))
            if like_raw is not None:
                like_success += 1
            print(f"[{index}/{len(sample)}] published={bool(published)} like={like_raw is not None} {url}")
        except Exception as exc:
            errors[type(exc).__name__] += 1
            print(f"[{index}/{len(sample)}] ERROR {type(exc).__name__}: {exc} {url}")

    report = {
        "schema_version": 1,
        "status": "compatible" if published_success >= int(SAMPLE_SIZE * 0.8) else "blocked",
        "checked_at": dt.datetime.now(dt.UTC).isoformat(),
        "source": "note public /n/ pages selected from official sitemap",
        "collection_paths": ["/sitemaps/*", "/*/n/*"],
        "forbidden_paths_used": False,
        "sitemap_url_count": len(urls),
        "sample_method": "60 URLs with lexicographically smallest SHA-256(URL); deterministic discovery probe only",
        "sample_count": SAMPLE_SIZE,
        "sample_set_sha256": hashlib.sha256("\n".join(sample).encode("utf-8")).hexdigest(),
        "published_at_extracted": published_success,
        "published_at_rate": published_success / SAMPLE_SIZE,
        "like_count_extracted": like_success,
        "like_count_rate": like_success / SAMPLE_SIZE,
        "published_year_counts": {str(year): count for year, count in sorted(years.items())},
        "like_count_observations_by_year": {str(year): len(values) for year, values in sorted(likes_by_year.items())},
        "errors": dict(sorted(errors.items())),
        "raw_html_persisted": False,
        "caveat": "This probe tests public-page metadata extraction only; it does not define or claim global top articles.",
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "compatible":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
