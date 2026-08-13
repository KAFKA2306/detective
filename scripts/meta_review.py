from __future__ import annotations

import datetime as dt
import json
import pathlib
import tomllib
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "detectors.toml"
OUTPUT = ROOT / "site" / "data" / "detectors.json"


def fetch_pypi(package: str) -> dict:
    url = f"https://pypi.org/pypi/{package}/json"
    request = urllib.request.Request(url, headers={"User-Agent": "KAFKA2306/detective meta-review"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def release_date(payload: dict, version: str) -> str | None:
    files = payload.get("releases", {}).get(version, [])
    dates = sorted(x.get("upload_time_iso_8601") for x in files if x.get("upload_time_iso_8601"))
    return dates[0] if dates else None


def main() -> None:
    with CATALOG.open("rb") as fh:
        catalog = tomllib.load(fh)

    rows = []
    for item in catalog.get("detector", []):
        row = dict(item)
        row["latest_version"] = None
        row["pinned_release_date"] = None
        row["update_available"] = None
        row["pypi_refresh_error"] = None
        try:
            payload = fetch_pypi(item["package"])
            latest = payload.get("info", {}).get("version")
            row["latest_version"] = latest
            row["pinned_release_date"] = release_date(payload, item["pinned_version"])
            row["update_available"] = bool(latest and latest != item["pinned_version"])
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            row["pypi_refresh_error"] = type(exc).__name__
        rows.append(row)

    output = {
        "schema_version": 1,
        "checked_at": dt.datetime.now(dt.UTC).isoformat(),
        "source": "PyPI JSON API + detectors.toml",
        "detectors": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
