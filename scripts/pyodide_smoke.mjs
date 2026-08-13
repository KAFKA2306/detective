import fs from "node:fs";
import { loadPyodide } from "pyodide";

const PYODIDE_VERSION = "0.27.7";
const PACKAGE = "pystylometry";
const PACKAGE_VERSION = "1.4.3";
const OUTPUT = "site/data/compatibility.json";

const output = {
  schema_version: 1,
  status: "failed",
  pyodide_version: PYODIDE_VERSION,
  python_line: "3.12",
  package: PACKAGE,
  package_version: PACKAGE_VERSION,
  metrics: ["compute_character_bigram_entropy", "compute_ngram_entropy(character, n=3)"],
  checked_at: new Date().toISOString(),
  error: null,
};

try {
  const pyodide = await loadPyodide({
    indexURL: `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`,
  });
  await pyodide.loadPackage("micropip");
  const micropip = pyodide.pyimport("micropip");
  await micropip.install(`${PACKAGE}==${PACKAGE_VERSION}`);
  micropip.destroy();
  const result = await pyodide.runPythonAsync(`
from pystylometry.ngrams import compute_character_bigram_entropy, compute_ngram_entropy
text = "日本語の技術文章をブラウザ内で解析する。公開OSSだけを使う。"
b = compute_character_bigram_entropy(text)
t = compute_ngram_entropy(text, n=3, ngram_type="character")
assert b.entropy >= 0
assert t.entropy >= 0
(b.entropy, t.entropy)
`);
  if (result?.destroy) result.destroy();
  output.status = "compatible";
} catch (error) {
  output.error = String(error?.stack || error);
  console.error(error);
  process.exitCode = 1;
} finally {
  fs.writeFileSync(OUTPUT, `${JSON.stringify(output, null, 2)}\n`);
  console.log(JSON.stringify(output, null, 2));
}
