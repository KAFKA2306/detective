const $ = (id) => document.getElementById(id);
let baselines = null;
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
    $("verdict").textContent = "判定できません";
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

function baselineUsable() {
  return baselines && ["pilot_ready", "ready"].includes(baselines.status) && baselines.metrics;
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

function nearestYear(metrics) {
  if (!baselineUsable()) return null;
  const configured = Array.isArray(baselines.distance_metrics)
    ? baselines.distance_metrics
    : Object.keys(baselines.metrics);
  const comparable = configured.filter((key) => baselines.metrics[key] && Number.isFinite(Number(metrics[key])));
  if (!comparable.length) return null;

  const distances = baselines.years.map((year) => {
    let sum = 0;
    let used = 0;
    for (const key of comparable) {
      const stat = baselines.metrics[key][String(year)];
      const value = Number(metrics[key]);
      if (!stat || !Number.isFinite(stat.mean) || !Number.isFinite(stat.std) || stat.std <= 0) continue;
      const z = (value - stat.mean) / stat.std;
      sum += z * z;
      used += 1;
    }
    return { year, distance: used ? Math.sqrt(sum / used) : Infinity, used };
  }).filter((x) => Number.isFinite(x.distance));

  distances.sort((a, b) => a.distance - b.distance);
  return distances[0] || null;
}

async function loadData() {
  const [baselineRes, detectorRes, compatibilityRes] = await Promise.all([
    fetch("./data/baselines.json", { cache: "no-store" }),
    fetch("./data/detectors.json", { cache: "no-store" }),
    fetch("./data/compatibility.json", { cache: "no-store" }),
  ]);
  baselines = await baselineRes.json();
  const catalog = await detectorRes.json();
  const compatibility = await compatibilityRes.json();

  const status = $("baseline-status");
  if (baselines.status === "ready") {
    status.textContent = `baseline ready · ${baselines.years.join("–")}`;
    status.className = "status ready";
  } else if (baselines.status === "pilot_ready") {
    const counts = Object.values(baselines.sample_counts || {});
    const n = counts.length && counts.every((value) => value === counts[0]) ? counts[0] : "?";
    status.textContent = `pilot baseline · ${n}件/年`;
    status.className = "status ready";
  } else {
    status.textContent = "年代baseline 未構築";
    status.className = "status blocked";
  }

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
  $("analyze").textContent = "簡易判定";
  if (response.error) {
    $("verdict").textContent = "判定できません";
    $("verdict-note").textContent = response.error;
    $("metrics").innerHTML = "";
    return;
  }

  const metrics = response.result;
  const nearest = nearestYear(metrics);
  const source = baselineLabel();
  if (nearest && baselines.status === "pilot_ready") {
    $("verdict").textContent = `pilotで最も近い年次分布: ${nearest.year}`;
    $("verdict-note").textContent = `${source}。8月同季節・正規化後先頭1,000文字のcharacter n-gram entropyによる記述的距離 ${nearest.distance.toFixed(2)}。AI生成の証明ではありません。`;
  } else if (nearest) {
    $("verdict").textContent = `最も近い年次分布: ${nearest.year}`;
    $("verdict-note").textContent = `${source}。実測baselineに対する標準化距離 ${nearest.distance.toFixed(2)}。AI生成の証明ではありません。`;
  } else {
    $("verdict").textContent = "年代判定はまだ実行しません";
    $("verdict-note").textContent = "実測baselineが利用できないためfail-closedです。pystylometryのPython正準関数が返した統計値だけを表示します。";
  }
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
  console.error(error);
});
