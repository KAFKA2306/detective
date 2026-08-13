import assert from "node:assert/strict";
import fs from "node:fs";

const app = fs.readFileSync("site/app.js", "utf8");
const worker = fs.readFileSync("site/worker.mjs", "utf8");

const networkSinks = ["fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource"];

// The pasted text must cross only the local Worker boundary from the UI.
const clickStart = app.indexOf('$("analyze").addEventListener');
const clearStart = app.indexOf('$("clear").addEventListener');
assert.ok(clickStart >= 0 && clearStart > clickStart, "analyze handler not found");
const analyzeHandler = app.slice(clickStart, clearStart);
assert.match(analyzeHandler, /analyzeInPython\(text\)/, "pasted text is not delegated to Python worker");
for (const sink of networkSinks) {
  assert.equal(analyzeHandler.includes(sink), false, `network sink ${sink} found in UI analyze path`);
}

// Network use in the Worker is allowed only during initialization (Pyodide/wheel/
// canonical analyzer loading). Once a text message is received, no network API may
// appear in that execution path.
const messageStart = worker.indexOf("self.onmessage =");
assert.ok(messageStart >= 0, "worker message handler not found");
const messageHandler = worker.slice(messageStart);
assert.match(messageHandler, /pyodide\.globals\.set\("detective_input_text", text\)/);
assert.match(messageHandler, /detective_analyze_json\(detective_input_text\)/);
for (const sink of networkSinks) {
  assert.equal(messageHandler.includes(sink), false, `network sink ${sink} found after pasted text enters Worker`);
}

console.log("privacy architecture ok: pasted text has no network sink in UI/Worker analysis paths");
