# detective

**文章の統計が違って見えても、それだけで「AIが書いた」とは言えない。**

`detective` は、2022–2026の公開技術文章を同じ条件で比較し、既存OSSが捉える文章統計の時系列変化を観測するメタレビュー基盤です。watermarkや独自AI detectorを前提にせず、年代・媒体・著者・文章長などのdistribution shiftそのものを測ります。

## Live

**GitHub Pages:** https://kafka2306.github.io/detective/

1,000文字以上の文章を貼ると、ブラウザ内のPythonでcharacter n-gram統計を計算し、現在の小規模pilotで2022–2026のどの年次分布に最も近いかを表示します。

これは**AI生成の証明ではありません**。現在の出力はあくまで実測pilotへの記述的距離です。

## 現在のpilot

- 対象: Zennの公開tech記事
- 年: 2022 / 2023 / 2024 / 2025 / 2026
- 同季節化: 各年8月1日12:00 JST近傍、公開日±7日
- 件数: **各年12件、計60件**
- 長さgate: `body_letters_count >= 1500`
- 解析窓: **Unicode NFKC + 空白正規化後の先頭1,000文字**
- raw本文: repositoryへ保存しない
- 保存: URL / published_at / cohort / SHA-256 / OSS由来派生統計 / provenance

歴史URLの候補発見にはZenn公式robots.txtが案内するsitemapを使います。13本のarticle sitemapをinventoryした結果、2026-08-13時点で **268,211 article URLs** を確認しています。sitemapの`lastmod`は公開日とはみなさず、候補発見だけに使い、年代ラベルは記事metadataの`published_at`で再検証します。

## 現在の実測結果

長さを揃えたpilotでは、年次分布はかなり重なっています。平均値は以下です。

| year | char bigram entropy | char trigram entropy |
|---:|---:|---:|
| 2022 | 8.438 | 9.025 |
| 2023 | 8.605 | 9.094 |
| 2024 | 8.505 | 9.062 |
| 2025 | 8.721 | 9.196 |
| 2026 | 8.585 | 9.165 |

full-textのまま比較した初期pilotではより大きい年次差が見えましたが、短文を含む長さ依存が混ざっていたため採用しませんでした。現在は全sampleと入力文を同じ1,000文字窓へ統制しています。

## Pagesアーキテクチャ

```text
GitHub Pages
  ↓
Web Worker
  ↓
Pyodide 0.27.7 / Python 3.12
  ↓
site/analyze.py  ← canonical Python implementation
  ↓
pystylometry 1.4.3
  ↓
character bigram / trigram entropy
  ↓
versioned yearly baseline JSON
```

Pythonの分析式をJavaScriptへ複製しません。`site/analyze.py`を、Pages Worker・WASM smoke test・offline baseline buildの3経路から共通利用します。

入力文はWeb Workerへ渡した後、分析pathから`fetch` / `XMLHttpRequest` / `sendBeacon` / `WebSocket` / `EventSource`へ到達しないことをCIの`privacy_architecture_test.mjs`でfail-close検査します。初回runtime取得ではPyodide CDNと公開wheelへの通信がありますが、貼り付け文章を判定APIへ送信するserver-side inferenceはありません。

## OSS比較対象

| OSS | 固定版 | 役割 | 環境 |
|---|---:|---|---|
| `pystylometry` | 1.4.3 | stylometry / Pages指標 | `detectors/pystylometry/uv.lock` |
| `stylometric-ai-detector` | 0.2.4 | 8特徴 + Random Forest baseline | `detectors/stylometric-ai-detector/uv.lock` |
| `explain-ai-generated-text` | 0.1.1.1.7 | 40+ linguistic features + SHAP系 baseline | `detectors/explain-ai-generated-text/uv.lock` |

各OSSは依存衝突を避けるため**独立した`pyproject.toml + uv.lock`**で固定します。比較対象の正式版・PyPI・source URLは [`detectors.toml`](detectors.toml) が正準です。

## 再現

```bash
uv sync --locked
uv run --locked python scripts/check_catalog.py

uv sync --project detectors/pystylometry --locked
uv run --project detectors/pystylometry --locked \
  python scripts/build_zenn_pystylometry_pilot_baseline.py
```

主なActions:

- `CI` — lock/catalog/JSON/privacy architecture
- `Pyodide compatibility` — WASM上でcanonical analyzerをsmoke test
- `OSS meta review` — PyPI version evidenceを週次更新
- `Zenn source probe` / `Zenn sitemap probe` — 外部source schemaをfail-close監査
- `Zenn sitemap metadata pilot` — metadata選定→派生統計→baselineを1 snapshotで更新
- `Deploy Pages` — evidence更新後も自動再deploy

## データ方針

Zenn本文は公開Git historyへ保存しません。取得時に一時処理し、`content_sha256`と派生統計だけを残します。詳細は [`docs/CORPUS_POLICY.md`](docs/CORPUS_POLICY.md)。

## 解釈上の境界

現在のpilotには、各年12件、8月限定、sitemap `lastmod` を候補発見に使うことによる編集履歴selection bias、著者構成差などの制約があります。したがって、表示される「近い年代」をClaude/AI生成判定へ読み替えてはいけません。

次の評価単位は、同じ仕組みのまま季節窓・sample数・cohortを増やし、年代差が再現するかを確認することです。

## 一次情報

- GitHub Pages custom workflows: https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- uv projects: https://docs.astral.sh/uv/guides/projects/
- uv locking: https://docs.astral.sh/uv/concepts/projects/sync/
- Pyodide 0.27.7: https://pyodide.org/en/0.27.7/
- pystylometry: https://pypi.org/project/pystylometry/1.4.3/
- stylometric-ai-detector: https://pypi.org/project/stylometric-ai-detector/0.2.4/
- explain-ai-generated-text: https://pypi.org/project/explain-ai-generated-text/0.1.1.1.7/
- Zenn robots.txt: https://zenn.dev/robots.txt
- Zenn利用規約: https://zenn.dev/terms

## Status

- [x] 空repoから初期化
- [x] GitHub Pages公開
- [x] Web Worker + Pyodide + canonical Python分析
- [x] `pystylometry==1.4.3` WASM compatibility PASS
- [x] 貼付テキストのnetwork sink CI検査
- [x] 3 detectorを独立`uv.lock`で固定
- [x] 公式sitemap経由の歴史URL inventory
- [x] 2022–2026同季節pilotを固定
- [x] 固定1,000文字pilot baselineを実測生成
- [x] Pagesでpilot年代距離を表示
- [ ] sample数・季節窓・cohortを増やして再現性を検証
- [ ] full-year/高engagement cohortを別系統で評価
