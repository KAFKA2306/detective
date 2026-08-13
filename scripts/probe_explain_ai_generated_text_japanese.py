from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "explain_ai_generated_text_japanese_compatibility.json"
PACKAGE = "explain-ai-generated-text"
VERSION = "0.1.1.1.7"

SAMPLES = {
    "english_control": "This is a short technical explanation written to test whether the upstream package can execute in its documented language setting. The text contains several complete sentences and ordinary punctuation.",
    "japanese_probe": "これは公開OSSの互換性を確認するための日本語テキストです。生成AIか人間かを判定する目的ではなく、日本語入力で既存パッケージが例外なく特徴量を返せるかだけを確認します。年代差や文章の出所について、この文章から結論を出すことはしません。",
}


def compact_result(value):  # noqa: ANN001
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == "features" and isinstance(item, dict):
                result["feature_count"] = len(item)
                result["feature_names_sample"] = sorted(map(str, item.keys()))[:20]
            elif isinstance(item, (str, int, float, bool)) or item is None:
                result[str(key)] = item
            else:
                result[str(key)] = type(item).__name__
        return result
    return {"return_type": type(value).__name__}


def main() -> None:
    report = {
        "schema_version": 1,
        "checked_at": dt.datetime.now(dt.UTC).isoformat(),
        "package": PACKAGE,
        "version": VERSION,
        "status": "blocked",
        "samples": {},
        "interpretation_gate": {
            "use_for_ai_authorship": False,
            "use_for_year_inference": False,
            "reason": "Compatibility probe only; upstream generalization to Japanese is not assumed.",
        },
        "provenance": {
            "pypi": "https://pypi.org/project/explain-ai-generated-text/0.1.1.1.7/",
            "source": "https://github.com/ShushantaTUD/Explain_AI_Generated_Text",
        },
    }

    try:
        from explain_ai_generated_text import shap_explainer
    except Exception as exc:
        report["import_error"] = f"{type(exc).__name__}: {exc}"
    else:
        success = 0
        for name, text in SAMPLES.items():
            try:
                value = shap_explainer(text)
                report["samples"][name] = {"status": "success", "result": compact_result(value)}
                success += 1
            except Exception as exc:
                report["samples"][name] = {"status": "blocked", "error": f"{type(exc).__name__}: {exc}"}
        if success == len(SAMPLES):
            report["status"] = "executes_on_japanese_not_validated"
        elif success:
            report["status"] = "partial"

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
