from __future__ import annotations

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

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATUS = ROOT / "reports" / "zenn_sitemap_status.json"
OUTPUT = ROOT / "reports" / "zenn_public_page_status.json"
USER_AGENT = "KAFKA2306-detective/0.1 (+https://github.com/KAFKA2306/detective)"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
SAMPLE_SIZE = 20
REQUEST_INTERVAL_SECONDS = 0.4
_last_request_at = 0.0

PUBLISHED_PATTERNS = [
    re.compile(r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)', re.I),
    re.compile(r'<time[^>]+datetime=["\']([^"\']+)["\']', re.I),
    re.compile(r'"datePublished"\s*:\s*"([^"]+)"'),
    re.compile(r'"published_at"\s*:\s*"([^"]+)"'),
    re.compile(r'"publishedAt"\s*:\s*"([^"]+)"'),
]
TYPE_PATTERNS = [
    re.compile(r'"article_type"\s*:\s*"(tech|idea)"', re.I),
    re.compile(r'"articleType"\s*:\s*"(tech|idea)"', re.I),
]


def fetch(url: str, *, sitemap: bool) -> bytes:
    global _last_request_at
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "zenn.dev":
        raise RuntimeError(f"refusing non-Zenn URL: {url}")
    if parsed.path.startswith("/api/") or parsed.path == "/search" or parsed.path.startswith("/search/"):
        raise RuntimeError(f"refusing unsupported path: {parsed.path}")
    if sitemap and not parsed.path.startswith("/sitemaps/"):
        raise RuntimeError(f"expected sitemap path: {url}")
    if not sitemap and "/articles/" not in parsed.path:
        raise RuntimeError(f"expected public article path: {url}")

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


def first_match(patterns: list[re.Pattern[str]], source: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(source)
        if match:
            return html.unescape(match.group(1))
    return None


def article_urls() -> list[str]:
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    if status.get("status") != "compatible":
        raise RuntimeError("official Zenn sitemap probe is not compatible")
    root = ET.fromstring(fetch(status["sitemap_index"], sitemap=True))
    sitemaps = [
        node.findtext("sm:loc", default="", namespaces=NS)
        for node in root.findall("sm:sitemap", NS)
    ]
    article_maps = [url for url in sitemaps if "/article" in urllib.parse.urlsplit(url).path]
    urls: list[str] = []
    for sitemap_url in article_maps:
        doc = ET.fromstring(fetch(sitemap_url, sitemap=True))
        for node in doc.findall("sm:url", NS):
            loc = node.findtext("sm:loc", default="", namespaces=NS)
            if loc and "/articles/" in urllib.parse.urlsplit(loc).path:
                urls.append(loc)
    return sorted(set(urls))


def deterministic_sample(urls: list[str]) -> list[str]:
    ranked = sorted((hashlib.sha256(url.encode()).hexdigest(), url) for url in urls)
    return [url for _, url in ranked[:SAMPLE_SIZE]]


def main() -> None:
    urls = article_urls()
    sample = deterministic_sample(urls)
    if len(sample) != SAMPLE_SIZE:
        raise RuntimeError(f"expected {SAMPLE_SIZE} sample URLs, got {len(sample)}")

    published_ok = 0
    type_ok = 0
    author_ok = 0
    errors: dict[str, int] = {}
    observations: list[dict[str, object]] = []

    for url in sample:
        try:
            source = fetch(url, sitemap=False).decode("utf-8", errors="replace")
            published_at = first_match(PUBLISHED_PATTERNS, source)
            article_type = first_match(TYPE_PATTERNS, source)
            path = urllib.parse.urlsplit(url).path.strip("/").split("/")
            author = path[0] if len(path) >= 3 and path[1] == "articles" else None
            published_ok += int(published_at is not None)
            type_ok += int(article_type is not None)
            author_ok += int(author is not None)
            observations.append({
                "source_url_sha256": hashlib.sha256(url.encode()).hexdigest(),
                "published_at_available": published_at is not None,
                "article_type_available": article_type is not None,
                "author_from_canonical_url": author is not None,
            })
        except Exception as exc:
            name = type(exc).__name__
            errors[name] = errors.get(name, 0) + 1

    report = {
        "schema_version": 1,
        "checked_at": dt.datetime.now(dt.UTC).isoformat(),
        "source": "Zenn official sitemap plus public /articles/ pages",
        "robots_source": "https://zenn.dev/robots.txt",
        "forbidden_paths_used": False,
        "sitemap_article_url_count": len(urls),
        "sample_count": len(sample),
        "sample_method": "20 URLs with lexicographically smallest SHA-256(URL)",
        "sample_set_sha256": hashlib.sha256("\n".join(sample).encode()).hexdigest(),
        "published_at_available": published_ok,
        "article_type_available": type_ok,
        "author_from_canonical_url": author_ok,
        "errors": dict(sorted(errors.items())),
        "raw_html_persisted": False,
        "observations": observations,
        "status": "compatible" if published_ok == len(sample) and type_ok == len(sample) and author_ok == len(sample) else "blocked",
        "note": "This probe validates public-page metadata availability only. It does not collect article bodies or define the confirmatory corpus.",
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "compatible":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
