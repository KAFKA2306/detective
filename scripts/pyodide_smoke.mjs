import fs from "node:fs";
import { loadPyodide } from "pyodide";

const PYODIDE_VERSION = "0.27.7";
const PACKAGE = "pystylometry";
const PACKAGE_VERSION = "1.4.3";
const OUTPUT = "site/data/compatibility.json";

const output = {
  schema_version: 2,
  status: "failed",
  pyodide_version: PYODIDE_VERSION,
  python_line: "3.12",
  package: PACKAGE,
  package_version: PACKAGE_VERSION,
  canonical_analyzer: "site/analyze.py",
  checked_at: new Date().toISOString(),
  error: null,
};

try {
  const pyodide = await loadPyodide();
  await pyodide.loadPackage("micropip");
  const micropip = pyodide.pyimport("micropip");
  await micropip.install(`${PACKAGE}==${PACKAGE_VERSION}`);
  micropip.destroy();

  const analyzerSource = fs.readFileSync("site/analyze.py", "utf8");
  await pyodide.runPythonAsync(analyzerSource);
  const smokeText = "日本語の技術文章をブラウザ内で解析する。公開OSSだけを使う。".repeat(80);
  pyodide.globals.set("detective_smoke_text", smokeText);
  const jsonResult = await pyodide.runPythonAsync("detective_analyze_json(detective_smoke_text)");
  pyodide.globals.delete("detective_smoke_text");
  const metrics = JSON.parse(jsonResult);
  if (metrics.analyzed_char_count !== 1000 || !Number.isFinite(metrics.char_bigram_entropy) || !Number.isFinite(metrics.char_trigram_entropy)) {
    throw new Error(`unexpected canonical analysis result: ${jsonResult}`);
  }
  output.status = "compatible";
  output.analysis_window_chars = metrics.analyzed_char_count;
} catch (error) {
  output.error = String(error?.stack || error);
  console.error(error);
  process.exitCode = 1;
} finally {
  fs.writeFileSync(OUTPUT, `${JSON.stringify(output, null, 2)}\n`);
  console.log(JSON.stringify(output, null, 2));
}
