from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

YEARS = range(2022, 2027)
MONTHS = range(1, 8)
TARGET_PER_STRATUM = 12
MIN_BODY_LETTERS = 1500
MAX_PER_AUTHOR_PER_STRATUM = 1


def parse_published_at(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("published_at must include a timezone")
    return parsed


def stable_rank(source_url: str) -> str:
    return hashlib.sha256(source_url.encode("utf-8")).hexdigest()


def is_eligible(row: dict[str, Any]) -> tuple[bool, str | None]:
    required = ("source_url", "published_at", "author_sha256", "body_letters_count", "article_type")
    missing = [field for field in required if field not in row]
    if missing:
        return False, f"missing:{','.join(missing)}"
    if row["article_type"] != "tech":
        return False, "not_tech"
    if not isinstance(row["body_letters_count"], int) or row["body_letters_count"] < MIN_BODY_LETTERS:
        return False, "body_too_short"
    try:
        published = parse_published_at(str(row["published_at"]))
    except (TypeError, ValueError):
        return False, "invalid_published_at"
    if published.year not in YEARS or published.month not in MONTHS:
        return False, "outside_confirmatory_window"
    if not str(row["source_url"]).startswith("https://zenn.dev/"):
        return False, "not_zenn_url"
    if not str(row["author_sha256"]):
        return False, "missing_author_hash"
    return True, None


def select(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    rejection_reasons: Counter[str] = Counter()

    for row in rows:
        accepted, reason = is_eligible(row)
        if not accepted:
            rejection_reasons[reason or "unknown"] += 1
            continue
        published = parse_published_at(str(row["published_at"]))
        candidate = dict(row)
        candidate["selection_rank_sha256"] = stable_rank(str(row["source_url"]))
        eligible[(published.year, published.month)].append(candidate)

    selected_rows: list[dict[str, Any]] = []
    strata: list[dict[str, Any]] = []

    for year in YEARS:
        for month in MONTHS:
            candidates = sorted(
                eligible.get((year, month), []),
                key=lambda row: (row["selection_rank_sha256"], row["source_url"]),
            )
            author_counts: Counter[str] = Counter()
            selected: list[dict[str, Any]] = []
            for row in candidates:
                author = str(row["author_sha256"])
                if author_counts[author] >= MAX_PER_AUTHOR_PER_STRATUM:
                    continue
                selected.append(row)
                author_counts[author] += 1
                if len(selected) == TARGET_PER_STRATUM:
                    break

            selected_rows.extend(selected)
            strata.append(
                {
                    "year": year,
                    "month": month,
                    "eligible_candidates": len(candidates),
                    "unique_authors": len({str(row["author_sha256"]) for row in candidates}),
                    "selected": len(selected),
                    "target": TARGET_PER_STRATUM,
                    "shortfall": TARGET_PER_STRATUM - len(selected),
                }
            )

    return {
        "schema_version": 1,
        "protocol": {
            "years": list(YEARS),
            "months": list(MONTHS),
            "target_per_stratum": TARGET_PER_STRATUM,
            "maximum_rows": len(list(YEARS)) * len(list(MONTHS)) * TARGET_PER_STRATUM,
            "minimum_body_letters": MIN_BODY_LETTERS,
            "article_type": "tech",
            "max_per_author_per_stratum": MAX_PER_AUTHOR_PER_STRATUM,
            "ordering": "ascending sha256(source_url), then source_url",
            "feature_blind_selection": True,
            "august_pilot_excluded": True,
        },
        "input_rows": len(rows),
        "eligible_rows": sum(len(items) for items in eligible.values()),
        "selected_rows": len(selected_rows),
        "rejection_reasons": dict(sorted(rejection_reasons.items())),
        "strata": strata,
        "selected": selected_rows,
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"line {line_number}: expected JSON object")
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="JSONL metadata rows; raw article text is not required")
    parser.add_argument("output", type=Path, help="selection manifest JSON")
    args = parser.parse_args()

    result = select(load_jsonl(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"selected {result['selected_rows']} of {result['protocol']['maximum_rows']} maximum rows")


if __name__ == "__main__":
    main()
