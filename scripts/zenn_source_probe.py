from __future__ import annotations

import datetime as dt
import json
import pathlib
import urllib.error
import urllib.request
import urllib.robotparser

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "zenn_source_status.json"
ROBOTS_URL = "https://zenn.dev/robots.txt"
API_URL = "https://zenn.dev/api/articles?order=latest&count=5&page=1"
USER_AGENT = "KAFKA2306-detective/0.1 (+https://github.com/KAFKA2306/detective)"
REQUIRED_ARTICLE_FIELDS = {
    "id",
    "slug",
    "liked_count",
    "body_letters_count",
    "article_type",
    "published_at",
    "path",
}


def get_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


def main() -> None:
    output: dict[str, object] = {
        "schema_version": 1,
        "status": "failed",
        "checked_at": dt.datetime.now(dt.UTC).isoformat(),
        "source": "zenn-undocumented-articles-json",
        "source_documented_by_zenn": False,
        "endpoint": API_URL,
        "robots_url": ROBOTS_URL,
        "robots_allows_endpoint": None,
        "article_count": 0,
        "article_fields": [],
        "required_fields_present": False,
        "published_at_min": None,
        "published_at_max": None,
        "liked_count_available": False,
        "next_page_present": False,
        "error": None,
    }

    try:
        robots_text = get_text(ROBOTS_URL)
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(ROBOTS_URL)
        parser.parse(robots_text.splitlines())
        allowed = parser.can_fetch(USER_AGENT, API_URL)
        output["robots_allows_endpoint"] = allowed
        if not allowed:
            raise RuntimeError("robots.txt does not allow the discovery endpoint")

        payload = json.loads(get_text(API_URL))
        articles = payload.get("articles")
        if not isinstance(articles, list) or not articles:
            raise RuntimeError("articles list is missing or empty")

        common_fields = set(articles[0])
        for article in articles[1:]:
            if isinstance(article, dict):
                common_fields &= set(article)
        output["article_count"] = len(articles)
        output["article_fields"] = sorted(common_fields)
        output["required_fields_present"] = REQUIRED_ARTICLE_FIELDS <= common_fields
        output["liked_count_available"] = all(
            isinstance(article.get("liked_count"), int)
            for article in articles
            if isinstance(article, dict)
        )
        output["next_page_present"] = "next_page" in payload

        dates = sorted(
            article.get("published_at")
            for article in articles
            if isinstance(article, dict) and isinstance(article.get("published_at"), str)
        )
        if dates:
            output["published_at_min"] = dates[0]
            output["published_at_max"] = dates[-1]

        if not output["required_fields_present"]:
            missing = sorted(REQUIRED_ARTICLE_FIELDS - common_fields)
            raise RuntimeError(f"required fields missing: {missing}")
        if not output["next_page_present"]:
            raise RuntimeError("next_page field is missing")

        output["status"] = "compatible"
    except (OSError, urllib.error.URLError, json.JSONDecodeError, RuntimeError) as exc:
        output["error"] = f"{type(exc).__name__}: {exc}"

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if output["status"] != "compatible":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
