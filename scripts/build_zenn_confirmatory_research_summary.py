from __future__ import annotations

import argparse
import json
import pathlib


def includes_zero(ci: list[float]) -> bool:
    return float(ci[0]) <= 0.0 <= float(ci[1])


def build(composition: dict, entropy: dict, ncd: dict, detector: dict) -> dict:
    hashes = {
        entropy["source_manifest_sha256"],
        ncd["source_manifest_sha256"],
        detector["source_manifest_sha256"],
    }
    if len(hashes) != 1:
        raise ValueError("source manifest hashes differ")

    selected_records = composition["selected_rows"]
    if entropy["measured_rows"] != selected_records or detector["measured_rows"] != selected_records:
        raise ValueError("record counts differ")

    bigram = entropy["endpoint_comparison_2026_minus_2022"]["char_bigram_entropy_bits"]
    trigram = entropy["endpoint_comparison_2026_minus_2022"]["char_trigram_entropy_bits"]
    detector_endpoint = detector["endpoint_2026_minus_2022"]

    return {
        "schema_version": 1,
        "source_manifest_sha256": next(iter(hashes)),
        "selected_records": selected_records,
        "composition": {
            "unique_authors": composition["author_concentration"]["unique_authors"],
            "authors_present_in_multiple_years": composition["author_concentration"]["authors_present_in_multiple_years"],
            "2026_records": composition["length_by_year"]["2026"]["n"],
        },
        "entropy": {
            "bigram_mean_difference_2026_minus_2022": bigram["mean_difference"],
            "bigram_bootstrap_95pct_ci": bigram["bootstrap_95pct_ci"],
            "bigram_ci_includes_zero": includes_zero(bigram["bootstrap_95pct_ci"]),
            "trigram_mean_difference_2026_minus_2022": trigram["mean_difference"],
            "trigram_bootstrap_95pct_ci": trigram["bootstrap_95pct_ci"],
            "trigram_ci_includes_zero": includes_zero(trigram["bootstrap_95pct_ci"]),
        },
        "ncd": {
            "pair_count": ncd["source_pair_count"],
            "month_gap_range": ncd["analysis"]["all_pairs"]["month_gap_range"],
            "month_gap_pearson_r": ncd["analysis"]["all_pairs"]["month_gap_ncd_pearson_r"],
            "different_author_month_gap_pearson_r": ncd["analysis"]["different_author_pairs"]["month_gap_ncd_pearson_r"],
            "same_author_pairs": ncd["analysis"]["same_author_pairs"]["n"],
            "inferential_author_effect_claimed": ncd["interpretation"]["inferential_author_effect_claimed"],
        },
        "detector_behavior": {
            "package": detector["package"],
            "version": detector["version"],
            "measured_rows": detector["measured_rows"],
            "errors": detector["errors"],
            "label_counts": detector["label_counts"],
            "mean_confidence_difference_2026_minus_2022": detector_endpoint["mean_difference"],
            "bootstrap_95pct_ci": detector_endpoint["bootstrap_95pct_ci"],
            "ci_includes_zero": includes_zero(detector_endpoint["bootstrap_95pct_ci"]),
            "labels_are_authorship_ground_truth": False,
            "artifact_sha256": detector["artifact_sha256"],
        },
        "conclusion": (
            "Across the frozen corpus, the entropy endpoint intervals and detector-confidence endpoint interval include zero, "
            "while NCD has near-zero linear correlation with publication-month distance. These measurements do not establish "
            "a stable temporal signal. The 2026 endpoint has four records, and same-author NCD has eight pairs, so those "
            "comparisons remain weak."
        ),
        "primary_sources": [
            "https://aclanthology.org/2026.findings-acl.682/",
            "https://arxiv.org/abs/2606.25152",
            "https://zenn.dev/robots.txt",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("composition", type=pathlib.Path)
    parser.add_argument("entropy", type=pathlib.Path)
    parser.add_argument("ncd", type=pathlib.Path)
    parser.add_argument("detector", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    inputs = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in [args.composition, args.entropy, args.ncd, args.detector]
    ]
    result = build(*inputs)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
