# detective

[![CI](https://github.com/KAFKA2306/detective/actions/workflows/ci.yml/badge.svg)](https://github.com/KAFKA2306/detective/actions/workflows/ci.yml)
[![Pyodide compatibility](https://github.com/KAFKA2306/detective/actions/workflows/compatibility.yml/badge.svg)](https://github.com/KAFKA2306/detective/actions/workflows/compatibility.yml)
[![Deploy Pages](https://github.com/KAFKA2306/detective/actions/workflows/pages.yml/badge.svg)](https://github.com/KAFKA2306/detective/actions/workflows/pages.yml)

**文章の統計が違って見えても、それだけで「AIが書いた」「この年代に書かれた」とは言えない。**

`detective` は、2022–2026の公開技術文章を同じ条件で比較し、2026年の研究と公開OSSが捉える文章統計の時系列変化を継続監査するメタレビュー基盤です。watermarkや独自AI detectorを前提にせず、年代・媒体・著者・文章長などのdistribution shiftそのものを測ります。

## Live

**GitHub Pages:** https://kafka2306.github.io/detective/

1,000文字以上の文章を貼ると、ブラウザ内Pythonで現在利用可能なstylometry指標を測定します。

**現在、年代を返しません。** `site/data/signal_validation.json` の `validated_year_inference_signal_count` が0件のためです。pilotで測定できることと、未知文章の年代をout-of-sampleで識別できることを分離しています。

## 2026研究から採用した原則

2026年研究では、単一detectorの高いbenchmark精度だけでなく、時間変化・domain shift・false positiveを監査する必要性が示されています。

- Cao et al., Findings of ACL 2026: human/LLM writingを長期trajectoryとして比較し、semantic / lexical / cognitive-emotional **driftとvariance**を測定。
- Ren et al. 2026: detectorを壊すdistribution shiftとして **temporal drift in human writing** を明示。
- Pudasaini et al. 2026: linguistic/stylometric detectorはin-domainで高性能でも、domain / generator shiftで大きく一般化性能が落ちることを報告。
- Dutta et al., ICWSM 2026: temporal signalsを使ったin-the-wild auditで、複数のAI-text detectorにfalse positiveがあることを報告。

そのためdetectiveでは、**測定 → out-of-sample検証 → 採否gate → Pages表示**の順を固定します。

## 現在のpilot

- 対象: Zennの公開tech記事
- 年: 2022 / 2023 / 2024 / 2025 / 2026
- 同季節化: 各年8月1日12:00 JST近傍、公開日±7日
- 件数: **各年12件、計60件**
- 長さgate: `body_letters_count >= 1500`
- 解析窓: **Unicode NFKC + 空白正規化後の先頭1,000文字**
- raw本文: repositoryへ保存しない
- 保存: URL / published_at / cohort / SHA-256 / OSS由来派生統計 / provenance

歴史URLの候補発見にはZenn公式robots.txtが案内するsitemapを使います。sitemapの`lastmod`は公開日とはみなさず、候補発見だけに使い、年代ラベルは記事metadataの`published_at`で再検証します。

## 実測1: character n-gram entropy

固定1,000文字pilotの平均値です。

| year | char bigram entropy | char trigram entropy |
|---:|---:|---:|
| 2022 | 8.438 | 9.025 |
| 2023 | 8.605 | 9.094 |
| 2024 | 8.505 | 9.062 |
| 2025 | 8.721 | 9.196 |
| 2026 | 8.585 | 9.165 |

分布は重なり、2指標だけでpublication yearを識別できるout-of-sample evidenceはありません。以前のPagesが行っていた「最も近い年次分布」表示は停止しました。

## 実測2: pystylometry NCD

`pystylometry==1.4.3` の `compute_compression_distance` を、同じ1,000文字の60記事へ適用しました。

- 評価: leave-one-out 1-nearest-neighbor
- 5年均等クラスのchance: **20.0%**
- 実測accuracy: **16 / 60 = 26.7%**
- within-year mean NCD: **0.8832**
- between-year mean NCD: **0.8875**
- gap: **0.0043**

同年と異年の距離がほぼ重なっているため、現在は `rejected_for_year_inference` です。

証跡: [`reports/zenn_pystylometry_ncd_year_separation.json`](reports/zenn_pystylometry_ncd_year_separation.json)

## 実測3: stylometric-ai-detector 0.2.4

2026年公開の既存OSSを、無改造で同じ60記事へ実行しました。上流自身がEnglish / single-dataset / pre-2024 trainingで、cross-language/domain generalizationを保証しないbaselineだと明記しています。

日本語pilotでは次のようになりました。

- 2022: **12 / 12 = AI**
- 2023: **12 / 12 = AI**
- 2024: **11 AI / 1 Human**
- 2025: **12 / 12 = AI**

2022年の公開技術記事まで全件AI扱いしているため、このAI/Human labelを日本語のauthorship判定や年代判定には使いません。

同OSSの8 surface featureについて2022→2026の記述的effect sizeも保存していますが、最大の `title_case_count` や `avg_sentence_len` は上流実装がEnglish Title Case、whitespace tokenization、`. ! ?` sentence splittingに依存するため、日本語年代差として採用しません。

証跡:

- [`reports/zenn_stylometric_ai_detector_2026_measurement.json`](reports/zenn_stylometric_ai_detector_2026_measurement.json)
- [`reports/zenn_2026_oss_distribution_shift.json`](reports/zenn_2026_oss_distribution_shift.json)

## 実測4: explain-ai-generated-text 0.1.1.1.7

固定uv環境で公式APIのimportをprobeした結果、`en_core_web_sm`が存在しないためimport時点でblockedになりました。

```text
OSError: [E050] Can't find model 'en_core_web_sm'.
```

日本語向けに上流OSSをpatchして通すことはせず、`blocked` evidenceとして保持します。

証跡: [`reports/explain_ai_generated_text_japanese_compatibility.json`](reports/explain_ai_generated_text_japanese_compatibility.json)

## Validation Gate

[`site/data/signal_validation.json`](site/data/signal_validation.json) がPagesの採否判定の正準です。

現在:

```text
validated_year_inference_signal_count = 0
status = measurement_only
```

ルール:

- pilot測定値だけで年代を返さない
- 単一metricで年を断定しない
- out-of-sample validationを必須にする
- blocked / failed OSSをpatchして合格扱いしない
- AI detectorのscoreを年代ラベルへ読み替えない

## Pagesアーキテクチャ

```text
2022–2026 public corpus
        ↓
GitHub Actions
  ├─ OSS measurement
  ├─ out-of-sample validation
  └─ signal_validation.json
        ↓
GitHub Pages
        ↓
Web Worker
        ↓
Pyodide 0.27.7 / Python 3.12
        ↓
site/analyze.py
        ↓
pystylometry 1.4.3
```

Pythonのブラウザ分析式をJavaScriptへ複製しません。`site/analyze.py`をPages Worker・WASM smoke test・offline baseline buildで共通利用します。

入力文はWeb Workerへ渡した後、分析pathから`fetch` / `XMLHttpRequest` / `sendBeacon` / `WebSocket` / `EventSource`へ到達しないことをCIでfail-close検査します。初回runtime取得ではPyodide CDNと公開wheelへの通信がありますが、貼り付け文章を判定APIへ送信するserver-side inferenceはありません。

## OSS比較対象

| OSS | 固定版 | 現在の扱い |
|---|---:|---|
| `pystylometry` | 1.4.3 | entropy測定 / NCD検証。NCD年代判定はreject |
| `stylometric-ai-detector` | 0.2.4 | 日本語AI/Human判定はreject。feature分布のみ監査 |
| `explain-ai-generated-text` | 0.1.1.1.7 | pinned環境でimport blocked |

各OSSは依存衝突を避けるため**独立した`pyproject.toml + uv.lock`**で固定します。正準catalogは [`detectors.toml`](detectors.toml) です。

## note cohort

Zennとは独立して、noteの`high-engagement` cohortも調査中です。

note公式robots.txtが案内するsitemapをprobeし、263,545件の`/n/` URLを確認しました。ただしsitemap `lastmod`は全件ほぼ2026年で公開年ラベルには使えず、静的HTML60件probeでは公開日は58/60取得できた一方、公開スキ数は0/60でした。このため、公式sitemapだけから「2022年TOP vs 2026年TOP」を捏造しません。

詳細: [Issue #4](https://github.com/KAFKA2306/detective/issues/4)

## 次の固定点

単一記事のyear classifierを先に作らず、2026研究に合わせて**集団の時系列trajectory**を強化します。

1. 8月12件/年から複数季節・より大きいsampleへ拡張
2. 年ごとのfeature distribution / variance / driftを再計算
3. 著者・topic・length・engagement confoundを監査
4. holdout / leave-one-outで再現したsignalだけ`validated_ready`候補にする
5. Pagesでは採用・棄却理由を同時表示

## 一次情報

- Cao et al., ACL 2026: https://aclanthology.org/2026.findings-acl.682/
- Ren et al. 2026: https://arxiv.org/abs/2606.25152
- Ren et al. code: https://github.com/kkr36/llm_detection
- Pudasaini et al. 2026: https://arxiv.org/abs/2603.23146
- Dutta et al., ICWSM 2026: https://ojs.aaai.org/index.php/ICWSM/article/view/42660
- pystylometry: https://pypi.org/project/pystylometry/1.4.3/
- stylometric-ai-detector: https://pypi.org/project/stylometric-ai-detector/0.2.4/
- explain-ai-generated-text: https://pypi.org/project/explain-ai-generated-text/0.1.1.1.7/
- GitHub Pages custom workflows: https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- uv projects: https://docs.astral.sh/uv/guides/projects/
- Pyodide 0.27.7: https://pyodide.org/en/0.27.7/
- Zenn robots.txt: https://zenn.dev/robots.txt
- Zenn利用規約: https://zenn.dev/terms

## Status

- [x] GitHub Pages公開
- [x] Web Worker + Pyodide + canonical Python分析
- [x] 3 detectorを独立`uv.lock`で固定
- [x] 2022–2026同季節pilotを固定
- [x] entropy-only nearest-year表示を停止
- [x] 2026 `stylometric-ai-detector`を60記事へ実測
- [x] 2026 `explain-ai-generated-text` compatibilityを実測
- [x] `pystylometry` NCDをleave-one-out評価
- [x] machine-readable validation gateを導入
- [ ] 複数季節・sample増加で時系列分布を再測定
- [ ] 著者/topic/length/engagement confoundを監査
- [ ] `validated_ready`に到達するsignalがあるか再評価
