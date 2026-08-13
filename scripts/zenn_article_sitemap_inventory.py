from __future__ import annotations

import datetime as dt
import gzip
import json
import pathlib
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX_STATUS = ROOT / "reports" / "zenn_sitemap_status.json"
OUTPUT = ROOT / "reports" / "zenn_article_sitemap_inventory.json"
USER_AGENT = "KAFKA2306-detective/0.1 (+https://github.com/KAFKA2306/detective)"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/gzip,application/xml,text/xml;q=0.9,*/*;q=0.1"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    if url.endswith(".gz"):
        return gzip.decompress(raw)
    return raw


def main() -> None:
    status = json.loads(INDEX_STATUS.read_text(encoding="utf-8"))
    if status.get("status") != "compatible":
        raise SystemExit("official sitemap index probe is not compatible")

    index_xml = fetch_bytes(status["sitemap_index"])
    root = ET.fromstring(index_xml)
    article_sitemaps = [
        node.findtext("sm:loc", default="", namespaces=NS)
        for node in root.findall("sm:sitemap", NS)
        if "article" in node.findtext("sm:loc", default="", namespaces=NS).rsplit("/", 1)[-1].lower()
    ]
    article_sitemaps = [url for url in article_sitemaps if url]
    if not article_sitemaps:
        raise SystemExit("no article sitemaps found")

    rows: list[dict] = []
    total_urls = 0
    all_lastmods: list[str] = []
    for url in article_sitemaps:
        doc = ET.fromstring(fetch_bytes(url))
        entries: list[tuple[str, str | None]] = []
        for node in doc.findall("sm:url", NS):
            loc = node.findtext("sm:loc", default="", namespaces=NS)
            lastmod = node.findtext("sm:lastmod", default="", namespaces=NS) or None
            if loc:
                entries.append((loc, lastmod))
        lastmods = sorted(value for _, value in entries if value)
        all_lastmods.extend(lastmods)
        total_urls += len(entries)
        rows.append(
            {
                "sitemap": url,
                "url_count": len(entries),
                "lastmod_min": lastmods[0] if lastmods else None,
                "lastmod_max": lastmods[-1] if lastmods else None,
                "first_url": entries[0][0] if entries else None,
                "last_url": entries[-1][0] if entries else None,
            }
        )
        print(f"{url}: {len(entries)} URLs")

    output = {
        "schema_version": 1,
        "status": "compatible",
        "checked_at": dt.datetime.now(dt.UTC).isoformat(),
        "source": "official-zenn-sitemap-index",
        "article_sitemap_count": len(article_sitemaps),
        "total_article_urls": total_urls,
        "lastmod_min": min(all_lastmods) if all_lastmods else None,
        "lastmod_max": max(all_lastmods) if all_lastmods else None,
        "sitemaps": rows,
        "note": "lastmod is sitemap modification metadata and is not treated as publication time",
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
