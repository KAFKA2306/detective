from __future__ import annotations

import collections
import datetime as dt
import gzip
import json
import pathlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports" / "note_sitemap_status.json"
OUTPUT = ROOT / "reports" / "note_article_sitemap_inventory.json"
USER_AGENT = "KAFKA2306-detective/0.1 (+https://github.com/KAFKA2306/detective)"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def fetch(url: str) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "note.com" or not parsed.path.startswith("/sitemaps/"):
        raise RuntimeError(f"refusing non-sitemap URL: {url}")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/gzip,application/xml,text/xml;q=0.9,*/*;q=0.1"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        raw = response.read()
    return gzip.decompress(raw) if url.endswith(".gz") or raw[:2] == b"\x1f\x8b" else raw


def parse_year(value: str) -> int | None:
    if len(value) < 4 or not value[:4].isdigit():
        return None
    return int(value[:4])


def main() -> None:
    status = json.loads(SOURCE.read_text(encoding="utf-8"))
    if status.get("status") != "compatible":
        raise SystemExit("note sitemap source probe is not compatible")
    children = status.get("sitemap", {}).get("child_sitemaps_sample", [])
    note_sitemaps = [
        url for url in children
        if isinstance(url, str) and pathlib.PurePosixPath(urllib.parse.urlsplit(url).path).name.startswith("notes")
    ]
    if not note_sitemaps:
        raise RuntimeError("no notes*.xml.gz sitemap found")

    rows: list[dict] = []
    total_urls = 0
    year_counts: collections.Counter[int] = collections.Counter()
    global_min: str | None = None
    global_max: str | None = None

    for url in note_sitemaps:
        root = ET.fromstring(fetch(url))
        tag = root.tag.rsplit("}", 1)[-1]
        if tag != "urlset":
            raise RuntimeError(f"expected urlset for {url}, got {tag}")
        count = 0
        lastmods: list[str] = []
        article_like = 0
        for node in root.findall("sm:url", NS):
            loc = node.findtext("sm:loc", default="", namespaces=NS)
            lastmod = node.findtext("sm:lastmod", default="", namespaces=NS)
            if not loc:
                continue
            count += 1
            path = urllib.parse.urlsplit(loc).path
            if "/n/" in path:
                article_like += 1
            if lastmod:
                lastmods.append(lastmod)
                year = parse_year(lastmod)
                if year is not None:
                    year_counts[year] += 1
        total_urls += count
        if lastmods:
            local_min, local_max = min(lastmods), max(lastmods)
            global_min = local_min if global_min is None else min(global_min, local_min)
            global_max = local_max if global_max is None else max(global_max, local_max)
        else:
            local_min = local_max = None
        rows.append(
            {
                "sitemap": url,
                "url_count": count,
                "article_like_url_count": article_like,
                "lastmod_min": local_min,
                "lastmod_max": local_max,
            }
        )
        print(f"{url}: {count} URLs, {article_like} /n/ URLs")

    report = {
        "schema_version": 1,
        "status": "compatible" if total_urls else "blocked",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "source": status["sitemap_url"],
        "note_sitemap_count": len(note_sitemaps),
        "total_url_count": total_urls,
        "lastmod_min": global_min,
        "lastmod_max": global_max,
        "lastmod_year_counts": {str(year): count for year, count in sorted(year_counts.items())},
        "sitemaps": rows,
        "caveat": "sitemap lastmod is inventory metadata, not a publication-date label",
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "compatible":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
