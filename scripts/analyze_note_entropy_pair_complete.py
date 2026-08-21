from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import statistics
from collections import defaultdict

from measure_note_high_engagement_entropy import bootstrap_ci, hedges_g

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_YEARS = (2022, 2026)
EXPECTED_SELECTED = 36


def validate_and_select_pair_complete(report: dict[str, object]) -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    records = report.get("records")
    if report.get("selected_rows_requested") != EXPECTED_SELECTED or not isinstance(records, list) or len(records) != EXPECTED_SELECTED:
        raise ValueError("expected the frozen 36-record entropy audit")
    if report.get("errors") not in ([], None):
        raise ValueError("source entropy audit contains fetch/parser errors")

    insufficient = [row for row in records if isinstance(row, dict) and row.get("measurement_status") == "insufficient_length"]
    if len(insufficient) != 1:
        raise ValueError("expected exactly one insufficient-length record")
    missing = insufficient[0]
    missing_year = int(missing["year"])
    if missing_year not in EXPECTED_YEARS:
        raise ValueError("insufficient-length record is outside comparison years")
    other_year = EXPECTED_YEARS[1] if missing_year == EXPECTED_YEARS[0] else EXPECTED_YEARS[0]

    counterparts = [
        row
        for row in records
        if isinstance(row, dict)
        and int(row["year"]) == other_year
        and int(row["month"]) == int(missing["month"])
        and int(row["selection_rank_within_year_month"]) == int(missing["selection_rank_within_year_month"])
    ]
    if len(counterparts) != 1 or counterparts[0].get("measurement_status") != "measured":
        raise ValueError("expected one measured counterpart with the same month and selection rank")
    counterpart = counterparts[0]

    selected = [
        row
        for row in records
        if isinstance(row, dict)
        and row.get("measurement_status") == "measured"
        and row.get("source_url_sha256") != counterpart.get("source_url_sha256")
    ]
    counts = {year: sum(int(row["year"]) == year for row in selected) for year in EXPECTED_YEARS}
    if counts != {2022: 17, 2026: 17}:
        raise ValueError(f"pair-complete sensitivity must be 17/17, got {counts}")
    return selected, missing, counterpart


def analyze(records: list[dict[str, object]]) -> dict[str, object]:
    by_year: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in records:
        by_year[int(row["year"])].append(row)

    metrics = ("char_bigram_entropy_bits", "char_trigram_entropy_bits")
    result: dict[str, object] = {"n_2022": len(by_year[2022]), "n_2026": len(by_year[2026])}
    for metric in metrics:
        left = [float(row[metric]) for row in by_year[2022]]
        right = [float(row[metric]) for row in by_year[2026]]
        result[metric] = {
            "mean_2022": statistics.mean(left),
            "mean_2026": statistics.mean(right),
            "mean_difference_2026_minus_2022": statistics.mean(right) - statistics.mean(left),
            "mean_difference_bootstrap_95pct_ci": bootstrap_ci(left, right),
            "hedges_g_2026_minus_2022": hedges_g(left, right),
        }
    return result


def build_summary(report: dict[str, object], source_sha256: str) -> dict[str, object]:
    selected, missing, counterpart = validate_and_select_pair_complete(report)
    analysis = analyze(selected)
    bigram_ci = analysis["char_bigram_entropy_bits"]["mean_difference_bootstrap_95pct_ci"]
    return {
        "schema_version": 1,
        "status": "pair_complete_sensitivity_analysis",
        "source_entropy_report_sha256": source_sha256,
        "source_selection_manifest_sha256": report.get("source_manifest_sha256"),
        "rule": "Keep the frozen 36-record selection unchanged. For this secondary sensitivity analysis only, omit the sole insufficient-length record and omit the selected record in the other comparison year with the same publication month and within-month selection rank.",
        "text_features_used_to_choose_counterpart": False,
        "excluded_insufficient_length": {
            "source_url_sha256": missing["source_url_sha256"],
            "year": missing["year"],
            "month": missing["month"],
            "selection_rank_within_year_month": missing["selection_rank_within_year_month"],
            "normalized_body_characters": missing["normalized_body_characters"],
        },
        "excluded_matched_counterpart": {
            "source_url_sha256": counterpart["source_url_sha256"],
            "year": counterpart["year"],
            "month": counterpart["month"],
            "selection_rank_within_year_month": counterpart["selection_rank_within_year_month"],
        },
        "analysis": analysis,
        "interpretation": (
            "The pair-complete bigram bootstrap interval includes zero; the earlier positive bigram interval does not persist after removing the same month/rank counterpart from 2026. "
            "The trigram interval also includes zero. This secondary analysis reduces the 17-versus-18 imbalance but does not make the editorially selected cohort population-representative."
            if bigram_ci is not None and bigram_ci[0] <= 0 <= bigram_ci[1]
            else "Pair-complete sensitivity result generated; interpret with the bounded editorial-cohort limitation."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()

    raw = args.input.read_bytes()
    report = json.loads(raw)
    summary = build_summary(report, hashlib.sha256(raw).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
