from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import random
import statistics
from collections import defaultdict

from measure_zenn_confirmatory_entropy import PREFIX_CHARACTERS, extract_article_text
from zenn_public_page_probe import fetch

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "reports" / "zenn_confirmatory_selection.json"
DEFAULT_OUTPUT = ROOT / "reports" / "zenn_confirmatory_detector_drift.json"
PACKAGE = "stylometric-ai-detector"
VERSION = "0.2.4"
BOOTSTRAP_REPLICATES = 10000
BOOTSTRAP_SEED = 20260821


def describe(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "median": None, "std_population": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "std_population": statistics.pstdev(values),
        "min": min(values),
        "max": max(values),
    }


def hedges_g(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(right) < 2:
        return None
    df = len(left) + len(right) - 2
    left_var = statistics.variance(left)
    right_var = statistics.variance(right)
    pooled_var = ((len(left) - 1) * left_var + (len(right) - 1) * right_var) / df
    if pooled_var <= 0:
        return 0.0 if statistics.mean(left) == statistics.mean(right) else None
    d = (statistics.mean(right) - statistics.mean(left)) / math.sqrt(pooled_var)
    return (1.0 - 3.0 / (4.0 * df - 1.0)) * d


def bootstrap_mean_difference_ci(
    left: list[float], right: list[float], *, replicates: int, seed: int
) -> list[float] | None:
    if not left or not right:
        return None
    rng = random.Random(seed)
    diffs: list[float] = []
    for _ in range(replicates):
        l = [left[rng.randrange(len(left))] for _ in left]
        r = [right[rng.randrange(len(right))] for _ in right]
        diffs.append(statistics.mean(r) - statistics.mean(l))
    diffs.sort()
    lo = diffs[math.floor(0.025 * (replicates - 1))]
    hi = diffs[math.ceil(0.975 * (replicates - 1))]
    return [lo, hi]


def label_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    labels = sorted({str(row["label"]) for row in rows})
    return {label: sum(1 for row in rows if str(row["label"]) == label) for label in labels}


def measure_row(row: dict[str, object]) -> dict[str, object]:
    from stylometric_ai_detector import extract_stylometric_features, predict

    url = str(row["source_url"])
    source = fetch(url, sitemap=False).decode("utf-8", errors="replace")
    normalized = extract_article_text(source)
    if len(normalized) < PREFIX_CHARACTERS:
        raise ValueError(f"normalized article body shorter than {PREFIX_CHARACTERS} characters: {url}")
    prefix = normalized[:PREFIX_CHARACTERS]
    features = extract_stylometric_features(prefix)
    prediction = predict(text=prefix)
    if not isinstance(features, dict) or not isinstance(prediction, dict):
        raise RuntimeError("unexpected upstream return type")
    probability = prediction.get("probability")
    label = prediction.get("label")
    if not isinstance(probability, (int, float)) or label is None:
        raise RuntimeError("upstream prediction missing label/probability")
    published_at = dt.datetime.fromisoformat(str(row["published_at"]).replace("Z", "+00:00"))
    return {
        "source_url": url,
        "published_at": published_at.isoformat(),
        "year": published_at.year,
        "month": published_at.month,
        "author_sha256": row["author_sha256"],
        "selection_rank_sha256": row["selection_rank_sha256"],
        "normalized_body_sha256": hashlib.sha256(normalized.encode()).hexdigest(),
        "normalized_prefix_sha256": hashlib.sha256(prefix.encode()).hexdigest(),
        "normalized_body_characters": len(normalized),
        "measured_characters": PREFIX_CHARACTERS,
        "features": {str(key): float(value) for key, value in features.items()},
        "label": str(label),
        "probability": float(probability),
        "raw_html_persisted": False,
        "article_body_persisted": False,
    }


def aggregate(records: list[dict[str, object]]) -> dict[str, object]:
    by_year: dict[int, list[dict[str, object]]] = defaultdict(list)
    by_stratum: dict[tuple[int, int], list[dict[str, object]]] = defaultdict(list)
    for row in records:
        by_year[int(row["year"])].append(row)
        by_stratum[(int(row["year"]), int(row["month"]))].append(row)

    feature_names = sorted(
        {str(name) for row in records for name in dict(row["features"]).keys()}
    )

    def group_summary(rows: list[dict[str, object]]) -> dict[str, object]:
        return {
            "n": len(rows),
            "probability": describe([float(row["probability"]) for row in rows]),
            "label_counts": label_counts(rows),
            "features": {
                feature: describe([float(dict(row["features"])[feature]) for row in rows])
                for feature in feature_names
                if all(feature in dict(row["features"]) for row in rows)
            },
        }

    years = {str(year): group_summary(rows) for year, rows in sorted(by_year.items())}
    strata = [
        {"year": year, "month": month, **group_summary(rows)}
        for (year, month), rows in sorted(by_stratum.items())
    ]

    left = [float(row["probability"]) for row in by_year.get(2022, [])]
    right = [float(row["probability"]) for row in by_year.get(2026, [])]
    endpoint = {
        "from_year": 2022,
        "to_year": 2026,
        "n_2022": len(left),
        "n_2026": len(right),
        "mean_probability_difference_2026_minus_2022": (
            statistics.mean(right) - statistics.mean(left) if left and right else None
        ),
        "mean_probability_difference_bootstrap_95pct_ci": bootstrap_mean_difference_ci(
            left, right, replicates=BOOTSTRAP_REPLICATES, seed=BOOTSTRAP_SEED
        ),
        "hedges_g_2026_minus_2022": hedges_g(left, right),
        "interpretation": (
            "Detector behavior only. The upstream model is an English, single-dataset, pre-2024 baseline; "
            "its labels/probabilities are not authorship ground truth for Japanese Zenn articles."
        ),
    }
    return {"feature_names": feature_names, "by_year": years, "by_year_month": strata, "endpoint": endpoint}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=pathlib.Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    input_bytes = args.input.read_bytes()
    selection = json.loads(input_bytes)
    selected = list(selection["selected"])
    if args.limit is not None:
        selected = selected[: args.limit]

    records: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for index, row in enumerate(selected, start=1):
        try:
            records.append(measure_row(row))
        except Exception as exc:
            errors.append({"source_url": str(row.get("source_url")), "error": f"{type(exc).__name__}: {exc}"})
        print(f"[{index}/{len(selected)}] measured={len(records)} errors={len(errors)}")

    report = {
        "schema_version": 1,
        "measured_at": dt.datetime.now(dt.UTC).isoformat(),
        "package": PACKAGE,
        "version": VERSION,
        "source_manifest": str(args.input.relative_to(ROOT)) if args.input.is_relative_to(ROOT) else str(args.input),
        "source_manifest_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "selected_rows_requested": len(selected),
        "measured_rows": len(records),
        "errors": errors,
        "protocol": {
            "source": "public Zenn /articles/ pages",
            "normalization": "Unicode NFKC, collapse all whitespace runs to one ASCII space, strip ends",
            "prefix_characters": PREFIX_CHARACTERS,
            "upstream_api": ["extract_stylometric_features", "predict"],
            "raw_html_persisted": False,
            "article_body_persisted": False,
            "outputs_are_authorship_ground_truth": False,
        },
        "upstream_limitations": {
            "training_language": "English",
            "training_scope": "single dataset",
            "training_period": "pre-2024",
            "generalization_warning": "Upstream warns that the baseline may not generalize across domains, languages, or AI model generations.",
            "source": "https://github.com/dinis-a/stylometric-ai-detector",
        },
        "records": records,
        "analysis": aggregate(records),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "source_manifest_sha256": report["source_manifest_sha256"],
        "selected_rows_requested": len(selected),
        "measured_rows": len(records),
        "errors": errors,
    }, ensure_ascii=False, indent=2))
    if errors or len(records) != len(selected):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
