from __future__ import annotations

import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports" / "zenn_stylometric_ai_detector_2026_measurement.json"
OUTPUT = ROOT / "reports" / "zenn_2026_oss_distribution_shift.json"


def pooled_sd(a: dict, b: dict) -> float | None:
    n1, n2 = int(a["n"]), int(b["n"])
    s1, s2 = float(a["std"]), float(b["std"])
    if n1 < 2 or n2 < 2:
        return None
    denom = n1 + n2 - 2
    variance = ((n1 - 1) * s1 * s1 + (n2 - 1) * s2 * s2) / denom
    return math.sqrt(variance) if variance > 0 else None


def effect(a: dict, b: dict) -> dict:
    mean_a, mean_b = float(a["mean"]), float(b["mean"])
    sd = pooled_sd(a, b)
    d = (mean_b - mean_a) / sd if sd else None
    return {
        "2022_mean": mean_a,
        "2026_mean": mean_b,
        "absolute_change": mean_b - mean_a,
        "pooled_sd": sd,
        "cohen_d_2026_minus_2022": d,
        "absolute_cohen_d": abs(d) if d is not None else None,
    }


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    y22 = source["years"]["2022"]
    y26 = source["years"]["2026"]
    features = {}
    for name in source["feature_names"]:
        row = effect(y22["features"][name], y26["features"][name])
        # Fixed input length is deliberately non-informative.
        row["eligible_for_interpretation"] = name != "char_count"
        features[name] = row

    ranked = sorted(
        (
            {"feature": name, **values}
            for name, values in features.items()
            if values["eligible_for_interpretation"] and values["absolute_cohen_d"] is not None
        ),
        key=lambda row: (-row["absolute_cohen_d"], row["feature"]),
    )

    output = {
        "schema_version": 1,
        "status": "descriptive_pilot_only",
        "source_package": source["package"],
        "source_version": source["version"],
        "cohort": source["input"]["cohort"],
        "samples_per_year": source["input"]["samples_per_year"],
        "analysis_window_chars": source["input"]["analysis_window_chars"],
        "comparison": "2022 vs 2026",
        "features": features,
        "ranked_by_absolute_cohen_d": ranked,
        "interpretation_gate": {
            "use_for_year_inference": False,
            "multiple_testing_claims": False,
            "causal_ai_claim": False,
            "reason": "These are descriptive effect sizes from a 12-per-year pilot. Upstream whitespace/sentence/case features are not validated for Japanese and may encode topic/formatting/English-tokenization artifacts.",
        },
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
