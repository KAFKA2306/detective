from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINES = ROOT / "site" / "data" / "baselines.json"
NCD = ROOT / "reports" / "zenn_pystylometry_ncd_year_separation.json"
STYLO = ROOT / "reports" / "zenn_stylometric_ai_detector_2026_measurement.json"
EXPLAIN = ROOT / "reports" / "explain_ai_generated_text_japanese_compatibility.json"
OUTPUT = ROOT / "site" / "data" / "signal_validation.json"


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    baseline = load(BASELINES)
    ncd = load(NCD)
    stylo = load(STYLO)
    explain = load(EXPLAIN)

    ncd_eval = ncd["evaluation"]
    ncd_pair = ncd["pairwise"]
    ncd_lift = float(ncd_eval["accuracy"]) - float(ncd_eval["chance_accuracy_balanced_5_class"])
    pair_gap = float(ncd_pair["between_year_mean_ncd"]) - float(ncd_pair["within_year_mean_ncd"])

    signals = [
        {
            "id": "pystylometry-character-ngram-entropy",
            "package": "pystylometry",
            "version": "1.4.3",
            "kind": "distribution_measurement",
            "status": "measured_not_validated",
            "use_for_year_inference": False,
            "evidence": {
                "sample_count": sum(int(v) for v in baseline.get("sample_counts", {}).values()),
                "years": baseline.get("years"),
                "metrics": baseline.get("distance_metrics"),
            },
            "reason": "The current pilot only measures per-year entropy distributions. It has no out-of-sample validation showing that the two entropy metrics identify publication year.",
        },
        {
            "id": "pystylometry-normalized-compression-distance",
            "package": "pystylometry",
            "version": "1.4.3",
            "kind": "language_independent_similarity",
            "status": "rejected_for_year_inference",
            "use_for_year_inference": False,
            "evidence": {
                "evaluation": ncd_eval["method"],
                "accuracy": ncd_eval["accuracy"],
                "chance_accuracy": ncd_eval["chance_accuracy_balanced_5_class"],
                "accuracy_lift": ncd_lift,
                "within_year_mean_ncd": ncd_pair["within_year_mean_ncd"],
                "between_year_mean_ncd": ncd_pair["between_year_mean_ncd"],
                "between_minus_within_mean_ncd": pair_gap,
            },
            "reason": "Leave-one-out 1-NN on the fixed 60-article pilot is only slightly above the balanced five-class chance rate, and within-year versus between-year NCD means are nearly identical.",
        },
        {
            "id": "stylometric-ai-detector-0.2.4",
            "package": "stylometric-ai-detector",
            "version": "0.2.4",
            "kind": "2026_ai_human_baseline",
            "status": "rejected_for_japanese_authorship_and_year_inference",
            "use_for_year_inference": False,
            "use_for_ai_authorship": False,
            "evidence": {
                "2022_label_counts": stylo["years"]["2022"]["upstream_label_counts"],
                "2023_label_counts": stylo["years"]["2023"]["upstream_label_counts"],
                "2024_label_counts": stylo["years"]["2024"]["upstream_label_counts"],
                "2025_label_counts": stylo["years"]["2025"]["upstream_label_counts"],
            },
            "reason": "The upstream English/pre-2024 benchmark labels essentially all historical Japanese Zenn pilot articles as AI, including all 12 samples from 2022 and 2023. Its own documentation warns against cross-language/domain generalization.",
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
        "validated_year_inference_signals": validated,
        "validated_year_inference_signal_count": len(validated),
        "policy": {
            "pilot_measurement_does_not_imply_year_inference": True,
            "single_metric_year_labels_forbidden": True,
            "out_of_sample_validation_required": True,
            "failed_or_blocked_upstream_oss_is_not_patched_into_acceptance": True,
        },
        "signals": signals,
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
