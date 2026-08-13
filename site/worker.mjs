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

  const analyzerUrl = new URL("./analyze.py", import.meta.url);
  const analyzerResponse = await fetch(analyzerUrl, { cache: "no-store" });
  if (!analyzerResponse.ok) {
    throw new Error(`canonical analyzer fetch failed: HTTP ${analyzerResponse.status}`);
  }
  await pyodide.runPythonAsync(await analyzerResponse.text());

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
    const jsonResult = await pyodide.runPythonAsync("detective_analyze_json(detective_input_text)");
    pyodide.globals.delete("detective_input_text");
    self.postMessage({ type: "result", id, result: JSON.parse(jsonResult) });
  } catch (error) {
    try { pyodide?.globals.delete("detective_input_text"); } catch (_) {}
    self.postMessage({ type: "result", id, error: String(error?.message || error) });
  }
};
