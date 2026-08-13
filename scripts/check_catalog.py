from __future__ import annotations

import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
REQUIRED = {
    "id",
    "package",
    "pinned_version",
    "role",
    "pypi_url",
    "repository_url",
    "license",
    "notes",
}


def main() -> None:
    with (ROOT / "detectors.toml").open("rb") as fh:
        data = tomllib.load(fh)
    detectors = data.get("detector", [])
    if not detectors:
        raise SystemExit("detectors.toml has no detector entries")
    seen: set[str] = set()
    for item in detectors:
        missing = REQUIRED - item.keys()
        if missing:
            raise SystemExit(f"{item.get('id', '<unknown>')}: missing {sorted(missing)}")
        if item["id"] in seen:
            raise SystemExit(f"duplicate detector id: {item['id']}")
        seen.add(item["id"])
        if not item["pypi_url"].startswith("https://pypi.org/project/"):
            raise SystemExit(f"{item['id']}: non-PyPI evidence URL")
        if not item["repository_url"].startswith("https://github.com/"):
            raise SystemExit(f"{item['id']}: non-GitHub repository URL")
    print(f"catalog ok: {len(detectors)} detectors")


if __name__ == "__main__":
    main()
