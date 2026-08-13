import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.mjs";

const PYODIDE_VERSION = "0.27.7";
const PACKAGE = "pystylometry";
const PACKAGE_VERSION = "1.4.3";

let pyodide;

async function initialize() {
  pyodide = await loadPyodide();
  await pyodide.loadPackage("micropip");
  const micropip = pyodide.pyimport("micropip");
  try {
    await micropip.install(`${PACKAGE}==${PACKAGE_VERSION}`);
  } finally {
    micropip.destroy();
  }
  await pyodide.runPythonAsync(`
import json
import math
from pystylometry.ngrams import compute_character_bigram_entropy, compute_ngram_entropy

def _finite(value):
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None

def detective_analyze(text):
    bigram = compute_character_bigram_entropy(text)
    trigram = compute_ngram_entropy(text, n=3, ngram_type="character")
    return json.dumps({
        "char_bigram_entropy": _finite(bigram.entropy),
        "char_bigram_perplexity": _finite(bigram.perplexity),
        "char_bigram_total": bigram.metadata.get("total_ngrams", 0),
        "char_bigram_unique": bigram.metadata.get("total_unique_ngrams", 0),
        "char_trigram_entropy": _finite(trigram.entropy),
        "char_trigram_perplexity": _finite(trigram.perplexity),
        "char_trigram_total": trigram.metadata.get("total_ngrams", 0),
        "char_trigram_unique": trigram.metadata.get("total_unique_ngrams", 0),
    }, ensure_ascii=False, allow_nan=False)
`);
  self.postMessage({
    type: "ready",
    pyodide_version: PYODIDE_VERSION,
    package: PACKAGE,
    package_version: PACKAGE_VERSION,
  });
}

const ready = initialize().catch((error) => {
  self.postMessage({ type: "init-error", error: String(error?.message || error) });
  throw error;
});

self.onmessage = async (event) => {
  const { type, id, text } = event.data || {};
  if (type !== "analyze") return;
  try {
    await ready;
    pyodide.globals.set("detective_input_text", text);
    const jsonResult = await pyodide.runPythonAsync("detective_analyze(detective_input_text)");
    pyodide.globals.delete("detective_input_text");
    self.postMessage({ type: "result", id, result: JSON.parse(jsonResult) });
  } catch (error) {
    try { pyodide?.globals.delete("detective_input_text"); } catch (_) {}
    self.postMessage({ type: "result", id, error: String(error?.message || error) });
  }
};
