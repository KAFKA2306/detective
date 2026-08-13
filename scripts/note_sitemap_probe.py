from __future__ import annotations

import datetime as dt
import gzip
import json
import pathlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "note_sitemap_status.json"
ROBOTS_URL = "https://note.com/robots.txt"
USER_AGENT = "KAFKA2306-detective/0.1 (+https://github.com/KAFKA2306/detective)"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def fetch(url: str, *, accept: str) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "note.com":
        raise RuntimeError(f"refusing non-note source: {url}")
    if parsed.path.startswith("/api/") or parsed.path == "/search" or parsed.path.startswith("/search/"):
        raise RuntimeError(f"refusing robots-disallowed collection path: {parsed.path}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def parse_robots(raw: str) -> tuple[list[str], list[str]]:
    disallow: list[str] = []
    sitemaps: list[str] = []
    applies_to_all = False
    for raw_line in raw.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        lower = key.lower()
        if lower == "user-agent":
            applies_to_all = value == "*"
        elif lower == "disallow" and applies_to_all and value:
            disallow.append(value)
        elif lower == "sitemap" and value:
            sitemaps.append(value)
    return disallow, sitemaps


def decode_xml(url: str, raw: bytes) -> bytes:
    if url.endswith(".gz") or raw[:2] == b"\x1f\x8b":
        return gzip.decompress(raw)
    return raw


def inspect_sitemap(url: str) -> dict:
    raw = fetch(url, accept="application/gzip,application/xml,text/xml;q=0.9,*/*;q=0.1")
    root = ET.fromstring(decode_xml(url, raw))
    tag = root.tag.rsplit("}", 1)[-1]
    if tag == "sitemapindex":
        children = [node.findtext("sm:loc", default="", namespaces=NS) for node in root.findall("sm:sitemap", NS)]
        children = [value for value in children if value]
        return {
            "kind": "sitemapindex",
            "child_sitemap_count": len(children),
            "child_sitemaps_sample": children[:10],
        }
    if tag == "urlset":
        urls = [node.findtext("sm:loc", default="", namespaces=NS) for node in root.findall("sm:url", NS)]
        urls = [value for value in urls if value]
        return {
            "kind": "urlset",
            "url_count": len(urls),
            "urls_sample": urls[:10],
        }
    raise RuntimeError(f"unexpected sitemap root: {root.tag}")


def main() -> None:
    checked_at = dt.datetime.now(dt.UTC).isoformat()
    report: dict = {
        "schema_version": 1,
        "status": "blocked",
        "checked_at": checked_at,
        "robots_url": ROBOTS_URL,
        "collector_policy": "robots+sitemap only; no /api/* or /search collection",
    }
    try:
        robots = fetch(ROBOTS_URL, accept="text/plain").decode("utf-8", errors="replace")
        disallow, sitemaps = parse_robots(robots)
        official = [url for url in sitemaps if url.startswith("https://note.com/sitemaps/")]
        if not official:
            raise RuntimeError("robots.txt exposes no note.com/sitemaps/ URL")
        if not any(rule.startswith("/api/") or rule == "/api/*" for rule in disallow):
            raise RuntimeError("expected /api/* disallow rule is absent")
        if "/search" not in disallow:
            raise RuntimeError("expected /search disallow rule is absent")

        sitemap_url = official[0]
        inspection = inspect_sitemap(sitemap_url)
        report.update(
            {
                "status": "compatible",
                "robots_disallow": disallow,
                "sitemap_url": sitemap_url,
                "sitemap": inspection,
                "error": None,
            }
        )
    except Exception as exc:  # fail closed and persist exact evidence
        report["error"] = f"{type(exc).__name__}: {exc}"

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "compatible":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
