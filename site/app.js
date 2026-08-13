const $ = (id) => document.getElementById(id);
let baselines = null;
let validation = null;
let workerReady = false;
let requestId = 0;
const pending = new Map();

const worker = new Worker("./worker.mjs", { type: "module" });

worker.addEventListener("message", (event) => {
  const msg = event.data || {};
  if (msg.type === "ready") {
    workerReady = true;
    $("runtime-status").textContent = `Pyodide ${msg.pyodide_version} / pystylometry ${msg.package_version}`;
    $("runtime-status").className = "status ready";
    $("analyze").disabled = false;
    return;
  }
  if (msg.type === "init-error") {
    $("runtime-status").textContent = "Python runtime unavailable";
    $("runtime-status").className = "status blocked";
    $("analyze").disabled = true;
    $("verdict").textContent = "測定できません";
    $("verdict-note").textContent = msg.error;
    $("result").hidden = false;
    return;
  }
  const resolve = pending.get(msg.id);
  if (resolve) {
    pending.delete(msg.id);
    resolve(msg);
  }
});

worker.addEventListener("error", (event) => {
  $("runtime-status").textContent = "Worker error";
  $("runtime-status").className = "status blocked";
  $("analyze").disabled = true;
  console.error(event);
});

function analyzeInPython(text) {
  return new Promise((resolve) => {
    const id = ++requestId;
    pending.set(id, resolve);
    worker.postMessage({ type: "analyze", id, text });
  });
}

function metricCard(label, value) {
  const n = Number(value);
  const formatted = Number.isFinite(n)
    ? (Number.isInteger(n) ? n.toLocaleString() : n.toFixed(3))
    : "—";
  return `<div class="metric"><strong>${formatted}</strong><span>${label}</span></div>`;
}

function baselineLabel() {
  if (!baselines) return "baseline unknown";
  const years = Array.isArray(baselines.years) ? `${baselines.years[0]}–${baselines.years.at(-1)}` : "year unknown";
  const counts = Object.values(baselines.sample_counts || {});
  const n = counts.length && counts.every((value) => value === counts[0]) ? counts[0] : "?";
  const detector = baselines.detector
    ? `${baselines.detector.package} ${baselines.detector.version}`
    : "detector unknown";
  return `Zenn tech ${years} / ${n}件・年 / ${baselines.cohort || "cohort unknown"} / ${detector}`;
}

function signalEvidence(signal) {
  const e = signal.evidence || {};
  if (signal.id === "pystylometry-normalized-compression-distance") {
    return `LOO accuracy ${(Number(e.accuracy) * 100).toFixed(1)}% / chance ${(Number(e.chance_accuracy) * 100).toFixed(1)}% / NCD gap ${Number(e.between_minus_within_mean_ncd).toFixed(4)}`;
  }
  if (signal.id === "stylometric-ai-detector-0.2.4") {
    const y22 = e["2022_label_counts"] || {};
    const y23 = e["2023_label_counts"] || {};
    return `2022 AI=${y22.AI || 0}/12 · 2023 AI=${y23.AI || 0}/12`;
  }
  if (signal.id === "explain-ai-generated-text-0.1.1.1.7") {
    return e.import_error || e.compatibility_status || "blocked";
  }
  if (signal.id === "pystylometry-character-ngram-entropy") {
    return `${e.sample_count || "?"} samples · ${(e.metrics || []).join(" / ")}`;
  }
  return "evidence recorded";
}

async function loadData() {
  const [baselineRes, detectorRes, compatibilityRes, validationRes] = await Promise.all([
    fetch("./data/baselines.json", { cache: "no-store" }),
    fetch("./data/detectors.json", { cache: "no-store" }),
    fetch("./data/compatibility.json", { cache: "no-store" }),
    fetch("./data/signal_validation.json", { cache: "no-store" }),
  ]);
  baselines = await baselineRes.json();
  const catalog = await detectorRes.json();
  const compatibility = await compatibilityRes.json();
  validation = await validationRes.json();

  const status = $("baseline-status");
  if (baselines.status === "validated_ready") {
    status.textContent = `validated baseline · ${baselines.years.join("–")}`;
    status.className = "status ready";
  } else if (baselines.status === "pilot_ready") {
    const counts = Object.values(baselines.sample_counts || {});
    const n = counts.length && counts.every((value) => value === counts[0]) ? counts[0] : "?";
    status.textContent = `pilot measurement only · ${n}件/年`;
    status.className = "status blocked";
  } else {
    status.textContent = "年代baseline 未検証";
    status.className = "status blocked";
  }

  const validatedCount = Number(validation.validated_year_inference_signal_count || 0);
  $("validation-status").textContent = validatedCount
    ? `validated signals · ${validatedCount}`
    : "year signals · 0 validated";
  $("validation-status").className = validatedCount ? "status ready" : "status blocked";
  $("validation-summary").textContent = validatedCount
    ? `${validatedCount}個のout-of-sample検証済みシグナルだけが年代表示に利用できます。`
    : "現時点で年代判定に採用できるシグナルは0件です。測定値は表示しますが、最寄り年は返しません。";
  $("validation-signals").innerHTML = validation.signals.map((signal) => `
    <article class="detector">
      <div class="detector-head"><h3>${signal.id}</h3><code>${signal.status}</code></div>
      <p>${signalEvidence(signal)}</p>
      <p>${signal.reason || ""}</p>
    </article>`).join("");

  $("checked-at").textContent = catalog.checked_at
    ? `PyPI checked ${catalog.checked_at.slice(0, 10)}`
    : "PyPI refresh pending";
  $("detectors").innerHTML = catalog.detectors.map((d) => `
    <article class="detector">
      <div class="detector-head"><h3>${d.id}</h3><code>${d.pinned_version}</code></div>
      <p>${d.notes || ""}</p>
      <p><a href="${d.pypi_url}" rel="noreferrer">PyPI</a> · <a href="${d.repository_url}" rel="noreferrer">source</a></p>
    </article>`).join("");

  const compat = $("compatibility");
  compat.textContent = compatibility.status === "compatible"
    ? `WASM smoke test: PASS (${compatibility.pyodide_version} / ${compatibility.package} ${compatibility.package_version})`
    : `WASM smoke test: ${compatibility.status}`;
}

$("analyze").disabled = true;
$("analyze").addEventListener("click", async () => {
  const text = $("text").value.trim();
  if (!text || !workerReady) return;
  $("analyze").disabled = true;
  $("analyze").textContent = "解析中…";
  $("result").hidden = false;
  $("verdict").textContent = "Pythonで解析中";
  $("verdict-note").textContent = "入力文はWeb Worker内のPyodideへ渡されます。";

  const response = await analyzeInPython(text);
  $("analyze").disabled = false;
  $("analyze").textContent = "簡易測定";
  if (response.error) {
    $("verdict").textContent = "測定できません";
    $("verdict-note").textContent = response.error;
    $("metrics").innerHTML = "";
    return;
  }

  const metrics = response.result;
  const source = baselineLabel();
  const validatedCount = Number(validation?.validated_year_inference_signal_count || 0);
  $("verdict").textContent = validatedCount ? "検証済み年代判定器の接続待ち" : "年代判定は保留しています";
  $("verdict-note").textContent = `${source}。現在の検証済み年代シグナルは${validatedCount}件です。pilot測定値だけから年を返しません。`;
  $("metrics").innerHTML = [
    ["入力文字数（正規化後）", metrics.normalized_char_count],
    ["解析文字数", metrics.analyzed_char_count],
    ["文字bigram entropy", metrics.char_bigram_entropy],
    ["文字bigram perplexity", metrics.char_bigram_perplexity],
    ["文字trigram entropy", metrics.char_trigram_entropy],
    ["文字trigram perplexity", metrics.char_trigram_perplexity],
    ["unique bigram", metrics.char_bigram_unique],
    ["unique trigram", metrics.char_trigram_unique],
  ].map(([k, v]) => metricCard(k, v)).join("");
});

$("clear").addEventListener("click", () => {
  $("text").value = "";
  $("result").hidden = true;
});

loadData().catch((error) => {
  $("baseline-status").textContent = "データ読込エラー";
  $("baseline-status").className = "status blocked";
  $("validation-status").textContent = "validation読込エラー";
  $("validation-status").className = "status blocked";
  console.error(error);
});
