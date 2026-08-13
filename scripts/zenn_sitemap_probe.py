from __future__ import annotations

import datetime as dt
import json
import pathlib
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "zenn_sitemap_status.json"
SITEMAP_INDEX = "https://zenn.dev/sitemaps/_index.xml"
USER_AGENT = "KAFKA2306-detective/0.1 (+https://github.com/KAFKA2306/detective)"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def classify(path: str) -> str:
    name = pathlib.PurePosixPath(path).name.lower()
    for token in ("article", "book", "user", "publication", "scrap"):
        if token in name:
            return token
    return "other"


def main() -> None:
    output: dict[str, object] = {
        "schema_version": 1,
        "status": "failed",
        "checked_at": dt.datetime.now(dt.UTC).isoformat(),
        "sitemap_index": SITEMAP_INDEX,
        "child_count": 0,
        "categories": {},
        "sample_children": [],
        "lastmod_min": None,
        "lastmod_max": None,
        "error": None,
    }
    try:
        raw = fetch_bytes(SITEMAP_INDEX)
        root = ET.fromstring(raw)
        children: list[dict[str, str | None]] = []
        for node in root.findall("sm:sitemap", NS):
            loc = node.findtext("sm:loc", default="", namespaces=NS)
            lastmod = node.findtext("sm:lastmod", default="", namespaces=NS) or None
            if not loc:
                continue
            children.append({"loc": loc, "lastmod": lastmod})

        if not children:
            raise RuntimeError("sitemap index contains no child sitemap entries")

        categories = Counter(classify(urlparse(row["loc"]).path) for row in children)
        lastmods = sorted(row["lastmod"] for row in children if row["lastmod"])
        sample = children[:5] + (children[-5:] if len(children) > 5 else [])

        output.update(
            status="compatible",
            child_count=len(children),
            categories=dict(sorted(categories.items())),
            sample_children=sample,
            lastmod_min=lastmods[0] if lastmods else None,
            lastmod_max=lastmods[-1] if lastmods else None,
        )
    except Exception as exc:  # evidence probe should persist exact failure class/message
        output["error"] = f"{type(exc).__name__}: {exc}"

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if output["status"] != "compatible":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
