from __future__ import annotations

import argparse
import json
import pathlib
import statistics
from typing import Any

from measure_note_high_engagement_entropy import bootstrap_ci, hedges_g

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "reports" / "note_high_engagement_entropy.json"
DEFAULT_OUTPUT = ROOT / "reports" / "note_high_engagement_entropy_sensitivity.json"
METRICS = ("char_bigram_entropy_bits", "char_trigram_entropy_bits")


def analyze_pair_complete(records: list[dict[str, Any]]) -> dict[str, Any]:
    insufficient = [row for row in records if row.get("measurement_status") == "insufficient_length"]
    if len(insufficient) != 1:
        raise ValueError("pair-complete sensitivity requires exactly one insufficient-length record")

    missing = insufficient[0]
    if int(missing["year"]) != 2022:
        raise ValueError("expected the insufficient-length record in the 2022 cohort")

    month = int(missing["month"])
    rank = int(missing["selection_rank_within_year_month"])
    counterpart = [
        row
        for row in records
        if int(row["year"]) == 2026
        and int(row["month"]) == month
        and int(row["selection_rank_within_year_month"]) == rank
    ]
    if len(counterpart) != 1 or counterpart[0].get("measurement_status") != "measured":
        raise ValueError("expected one measurable 2026 counterpart with the same month and selection rank")

    excluded_hashes = {
        str(missing["source_url_sha256"]),
        str(counterpart[0]["source_url_sha256"]),
    }
    measured = [
        row
        for row in records
        if row.get("measurement_status") == "measured"
        and str(row["source_url_sha256"]) not in excluded_hashes
    ]
    by_year = {
        year: [row for row in measured if int(row["year"]) == year]
        for year in (2022, 2026)
    }
    if len(by_year[2022]) != len(by_year[2026]):
        raise ValueError("pair-complete sensitivity must produce equal year sample sizes")

    comparisons: dict[str, Any] = {}
    for metric in METRICS:
        left = [float(row[metric]) for row in by_year[2022]]
        right = [float(row[metric]) for row in by_year[2026]]
        comparisons[metric] = {
            "n_2022": len(left),
            "n_2026": len(right),
            "mean_2022": statistics.mean(left),
            "mean_2026": statistics.mean(right),
            "mean_difference_2026_minus_2022": statistics.mean(right) - statistics.mean(left),
            "bootstrap_95pct_ci": bootstrap_ci(left, right),
            "hedges_g_2026_minus_2022": hedges_g(left, right),
        }

    return {
        "analysis": "pair-complete sensitivity",
        "rule": "Keep the frozen 36-record selection unchanged. For secondary analysis only, exclude the sole insufficient-length 2022 record and the 2026 record with the same publication month and selection rank.",
        "excluded_records": [
            {
                "year": int(missing["year"]),
                "month": month,
                "selection_rank_within_year_month": rank,
                "source_url_sha256": str(missing["source_url_sha256"]),
                "reason": "insufficient_length_under_1000_character_contract",
            },
            {
                "year": int(counterpart[0]["year"]),
                "month": month,
                "selection_rank_within_year_month": rank,
                "source_url_sha256": str(counterpart[0]["source_url_sha256"]),
                "reason": "matched_counterpart_excluded_for_pair_complete_sensitivity",
            },
        ],
        "analyzed_rows": len(measured),
        "comparisons": comparisons,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=pathlib.Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source = json.loads(args.input.read_text(encoding="utf-8"))
    records = source.get("records")
    if not isinstance(records, list):
        raise ValueError("measurement report does not contain records")

    result = {
        "schema_version": 1,
        "source_manifest_sha256": source.get("source_manifest_sha256"),
        "source_measured_rows": source.get("measured_rows"),
        "source_insufficient_length_rows": source.get("insufficient_length_rows"),
        **analyze_pair_complete(records),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
