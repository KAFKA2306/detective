from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIRMATORY = ROOT / "reports" / "zenn_confirmatory_research_summary.json"
EXPLAIN = ROOT / "reports" / "explain_ai_generated_text_japanese_compatibility.json"
OUTPUT = ROOT / "site" / "data" / "signal_validation.json"


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    confirmatory = load(CONFIRMATORY)
    explain = load(EXPLAIN)

    entropy = confirmatory["entropy"]
    ncd = confirmatory["ncd"]
    detector = confirmatory["detector_behavior"]

    signals = [
        {
            "id": "pystylometry-character-ngram-entropy",
            "package": "pystylometry",
            "version": "1.4.3",
            "kind": "distribution_measurement",
            "status": "rejected_for_year_inference",
            "use_for_year_inference": False,
            "evidence": {
                "sample_count": confirmatory["selected_records"],
                "2026_record_count": confirmatory["composition"]["2026_records"],
                "bigram_mean_difference_2026_minus_2022": entropy[
                    "bigram_mean_difference_2026_minus_2022"
                ],
                "bigram_bootstrap_95pct_ci": entropy["bigram_bootstrap_95pct_ci"],
                "bigram_ci_includes_zero": entropy["bigram_ci_includes_zero"],
                "trigram_mean_difference_2026_minus_2022": entropy[
                    "trigram_mean_difference_2026_minus_2022"
                ],
                "trigram_bootstrap_95pct_ci": entropy["trigram_bootstrap_95pct_ci"],
                "trigram_ci_includes_zero": entropy["trigram_ci_includes_zero"],
            },
            "reason": "The frozen confirmatory corpus does not establish a stable entropy trend: both 2022-to-2026 endpoint bootstrap intervals include zero, and the 2026 endpoint has only four records.",
        },
        {
            "id": "pystylometry-normalized-compression-distance",
            "package": "pystylometry",
            "version": "1.4.3",
            "kind": "language_independent_similarity",
            "status": "rejected_for_year_inference",
            "use_for_year_inference": False,
            "evidence": ncd,
            "reason": "Across 24,310 confirmatory pairs, NCD has near-zero linear correlation with publication-month distance. Same-author evidence is only eight pairs, so no inferential author effect is claimed.",
        },
        {
            "id": "stylometric-ai-detector-0.2.4",
            "package": detector["package"],
            "version": detector["version"],
            "kind": "2026_ai_human_baseline",
            "status": "rejected_for_japanese_authorship_and_year_inference",
            "use_for_year_inference": False,
            "use_for_ai_authorship": False,
            "evidence": {
                "measured_rows": detector["measured_rows"],
                "label_counts": detector["label_counts"],
                "mean_confidence_difference_2026_minus_2022": detector[
                    "mean_confidence_difference_2026_minus_2022"
                ],
                "bootstrap_95pct_ci": detector["bootstrap_95pct_ci"],
                "ci_includes_zero": detector["ci_includes_zero"],
                "labels_are_authorship_ground_truth": detector[
                    "labels_are_authorship_ground_truth"
                ],
            },
            "reason": "On the frozen confirmatory corpus, the upstream detector labels 219 of 221 Japanese Zenn articles as AI and its 2022-to-2026 confidence-difference interval includes zero. These labels are not authorship ground truth and are not usable for year inference.",
        },
        {
            "id": "explain-ai-generated-text-0.1.1.1.7",
            "package": "explain-ai-generated-text",
            "version": "0.1.1.1.7",
            "kind": "2026_explainable_linguistic_detector",
            "status": "blocked",
            "use_for_year_inference": False,
            "use_for_ai_authorship": False,
            "evidence": {
                "compatibility_status": explain.get("status"),
                "import_error": explain.get("import_error"),
            },
            "reason": "The pinned upstream package does not import in its isolated uv environment because en_core_web_sm is absent. detective does not patch the upstream package to force Japanese execution.",
        },
    ]

    validated = [row["id"] for row in signals if row.get("use_for_year_inference")]
    output = {
        "schema_version": 1,
        "status": "validated_ready" if validated else "measurement_only",
        "research_decision": {
            "year_inference": "stop_current_corpus",
            "source": "reports/zenn_confirmatory_research_summary.json",
            "selected_records": confirmatory["selected_records"],
            "reason": confirmatory["conclusion"],
        },
        "validated_year_inference_signals": validated,
        "validated_year_inference_signal_count": len(validated),
        "policy": {
            "pilot_measurement_does_not_imply_year_inference": True,
            "single_metric_year_labels_forbidden": True,
            "out_of_sample_validation_required": True,
            "failed_or_blocked_upstream_oss_is_not_patched_into_acceptance": True,
            "confirmatory_negative_result_stops_same_angle_research": True,
        },
        "signals": signals,
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
