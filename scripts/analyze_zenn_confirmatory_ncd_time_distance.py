from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
from collections import defaultdict


def month_gap(pair: dict[str, object]) -> int:
    left = int(pair["year_a"]) * 12 + int(pair["month_a"])
    right = int(pair["year_b"]) * 12 + int(pair["month_b"])
    return abs(right - left)


def pearson_correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    denominator = math.sqrt(
        sum((x - mean_x) ** 2 for x in xs) * sum((y - mean_y) ** 2 for y in ys)
    )
    if denominator == 0:
        return None
    return numerator / denominator


def describe(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


def analyze(report: dict[str, object]) -> dict[str, object]:
    pairs = list(report["pairs"])
    same_author = [pair for pair in pairs if bool(pair["same_author"])]
    different_author = [pair for pair in pairs if not bool(pair["same_author"])]

    def correlation(rows: list[dict[str, object]]) -> float | None:
        return pearson_correlation(
            [float(month_gap(pair)) for pair in rows],
            [float(pair["ncd"]) for pair in rows],
        )

    same_by_gap: dict[int, list[float]] = defaultdict(list)
    for pair in same_author:
        same_by_gap[month_gap(pair)].append(float(pair["ncd"]))

    return {
        "schema_version": 1,
        "source_manifest_sha256": report.get("source_manifest_sha256"),
        "source_pair_count": len(pairs),
        "analysis": {
            "all_pairs": {
                "n": len(pairs),
                "month_gap_ncd_pearson_r": correlation(pairs),
                "month_gap_range": [min(map(month_gap, pairs)), max(map(month_gap, pairs))] if pairs else None,
            },
            "different_author_pairs": {
                "n": len(different_author),
                "month_gap_ncd_pearson_r": correlation(different_author),
            },
            "same_author_pairs": {
                **describe([float(pair["ncd"]) for pair in same_author]),
                "month_gap_range": [min(map(month_gap, same_author)), max(map(month_gap, same_author))]
                if same_author
                else None,
                "by_month_gap": [
                    {"month_gap": gap, **describe(values)}
                    for gap, values in sorted(same_by_gap.items())
                ],
            },
        },
        "interpretation": {
            "inferential_author_effect_claimed": False,
            "reason": "Same-author pairs are sparse and pair observations are not statistically independent when an author contributes more than two documents.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    report = json.loads(args.input.read_text(encoding="utf-8"))
    result = analyze(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
