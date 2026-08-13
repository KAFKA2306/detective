const $ = (id) => document.getElementById(id);
let baselines = null;

function surfaceProfile(text) {
  const chars = Array.from(text);
  const words = text.trim() ? text.trim().split(/\s+/u) : [];
  const punctuation = chars.filter((c) => /[\p{P}\p{S}]/u.test(c)).length;
  const sentences = text.split(/[。！？.!?]+/u).map((s) => s.trim()).filter(Boolean);
  const avgWord = words.length ? words.reduce((n, w) => n + Array.from(w).length, 0) / words.length : 0;
  return {
    char_count: chars.length,
    word_count: words.length,
    avg_word_len: avgWord,
    punct_count: punctuation,
    sentence_count: sentences.length,
    avg_sentence_len: sentences.length ? words.length / sentences.length : 0,
    upper_case_count: words.filter((w) => /[A-Z]/.test(w) && w === w.toUpperCase()).length,
    title_case_count: words.filter((w) => /^[A-Z][a-z]+$/.test(w)).length,
  };
}

function metricCard(label, value) {
  const formatted = Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
  return `<div class="metric"><strong>${formatted}</strong><span>${label}</span></div>`;
}

function nearestYear(profile) {
  if (!baselines || baselines.status !== "ready" || !baselines.metrics) return null;
  const comparable = Object.keys(profile).filter((key) => baselines.metrics[key]);
  if (!comparable.length) return null;
  const distances = baselines.years.map((year) => {
    let sum = 0;
    let used = 0;
    for (const key of comparable) {
      const stat = baselines.metrics[key][String(year)];
      if (!stat || !Number.isFinite(stat.mean) || !Number.isFinite(stat.std) || stat.std <= 0) continue;
      const z = (profile[key] - stat.mean) / stat.std;
      sum += z * z;
      used += 1;
    }
    return { year, distance: used ? Math.sqrt(sum / used) : Infinity, used };
  }).filter((x) => Number.isFinite(x.distance));
  distances.sort((a, b) => a.distance - b.distance);
  return distances[0] || null;
}

async function loadData() {
  const [baselineRes, detectorRes] = await Promise.all([
    fetch("./data/baselines.json", { cache: "no-store" }),
    fetch("./data/detectors.json", { cache: "no-store" }),
  ]);
  baselines = await baselineRes.json();
  const catalog = await detectorRes.json();

  const status = $("baseline-status");
  if (baselines.status === "ready") {
    status.textContent = `baseline ready · ${baselines.years.join("–")}`;
    status.className = "status ready";
  } else {
    status.textContent = "年代baseline 未構築";
    status.className = "status blocked";
  }

  $("checked-at").textContent = catalog.checked_at ? `PyPI checked ${catalog.checked_at.slice(0,10)}` : "PyPI refresh pending";
  $("detectors").innerHTML = catalog.detectors.map((d) => `
    <article class="detector">
      <div class="detector-head"><h3>${d.id}</h3><code>${d.pinned_version}</code></div>
      <p>${d.notes || ""}</p>
      <p><a href="${d.pypi_url}" rel="noreferrer">PyPI</a> · <a href="${d.repository_url}" rel="noreferrer">source</a></p>
    </article>`).join("");
}

$("analyze").addEventListener("click", () => {
  const text = $("text").value.trim();
  if (!text) return;
  const profile = surfaceProfile(text);
  const nearest = nearestYear(profile);
  $("result").hidden = false;
  if (nearest) {
    $("verdict").textContent = `最も近い年次分布: ${nearest.year}`;
    $("verdict-note").textContent = `標準化距離 ${nearest.distance.toFixed(2)}。これは著者属性やAI生成を証明する値ではありません。`;
  } else {
    $("verdict").textContent = "年代判定はまだ実行しません";
    $("verdict-note").textContent = "2022–2026の実測baselineが0件のためfail-closedです。下には公開baseline OSSと同じ表層特徴のプロファイルだけを表示します。";
  }
  $("metrics").innerHTML = [
    ["文字数", profile.char_count],
    ["空白区切り語数", profile.word_count],
    ["平均語長", profile.avg_word_len],
    ["句読点・記号", profile.punct_count],
    ["文数", profile.sentence_count],
    ["平均文長（語）", profile.avg_sentence_len],
    ["全大文字語", profile.upper_case_count],
    ["Title Case語", profile.title_case_count],
  ].map(([k,v]) => metricCard(k,v)).join("");
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
