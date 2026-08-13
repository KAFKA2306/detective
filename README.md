# detective

**文章の統計が違って見えても、それだけで「AIが書いた」とは言えない。**

同じ日本語の技術文章でも、年代、媒体、著者、編集、翻訳などが変われば分布は動きます。たとえば2022年の文章と2026年の文章に差が見えたとき、その差を生成AIだけの影響として扱うと、年代差や媒体差をAI判定へ混ぜてしまいます。

detectiveは、2022–2026の公開技術文章を年次で固定し、既存OSSを同じ条件で継続比較して、文章統計の時系列分布変化を観測するメタレビュー基盤です。ここで初めて stylometry、AI-text detection、Pyodide、character n-gram などの技術を使います。watermark detectorではなく、実測baselineが足りないときは判定を返しません。

READMEの入口は [`KAFKA2306/articles#34`](https://github.com/KAFKA2306/articles/issues/34) の「広い問題 → 具体例 → 技術」の編集原則を維持し、年代差や統計的距離をAI生成の断定へ広げません。

## 目的

- 2022–2026 の公開技術文章を年次で固定・監査する
- 既存の stylometry / AI-text detection OSS を `uv` で再現可能に管理する
- 自前detectorを新設せず、OSSごとの出力・前提・限界を横並びで比較する
- GitHub Pages に「テキストを貼るだけ」の簡易判定UIを公開する
- 実測baselineが未構築・不十分な場合は年代推定を返さず fail-closed にする

## 現在のアーキテクチャ

```text
2022–2026 public corpus
        ↓
Actions: provenance / OSS meta review / baseline build
        ↓
static baseline artifacts
        ↓
GitHub Pages
        ↓
Web Worker
        ↓
Pyodide 0.27.7 (Python 3.12)
        ↓
pystylometry 1.4.3 canonical Python functions
        ↓
character bigram / trigram entropy → year-distance UI
```

Pages側で分析式をJavaScriptへ複製しません。入力文はWeb Worker内のPythonへ渡し、`pystylometry`の公開関数を直接呼びます。

現在ブラウザで採用している指標は、日本語の無分かち書きでも使いやすいcharacter n-gram系です。

- `compute_character_bigram_entropy`
- `compute_ngram_entropy(..., n=3, ngram_type="character")`

`site/data/compatibility.json` はActionsのWASM smoke testで更新します。2026-08-13時点で **Pyodide 0.27.7 + pystylometry 1.4.3 = compatible** を実測確認済みです。

## OSS比較対象

| OSS | 固定版 | 役割 | 実行環境 |
|---|---:|---|---|
| `pystylometry` | 1.4.3 | stylometry / browser指標 | `detectors/pystylometry/uv.lock` |
| `stylometric-ai-detector` | 0.2.4 | 8特徴 + Random Forest baseline | `detectors/stylometric-ai-detector/uv.lock` |
| `explain-ai-generated-text` | 0.1.1.1.7 | 40+ linguistic features + SHAP系 baseline | `detectors/explain-ai-generated-text/uv.lock` |

各OSSは依存衝突を避けるため**独立した`pyproject.toml + uv.lock`**で管理します。比較対象の正式版・PyPI・source URLは [`detectors.toml`](detectors.toml) を正準とします。

## 再現性

rootの運用スクリプトも`uv`管理です。

```bash
uv sync --locked
uv run --locked python scripts/check_catalog.py
uv run --locked python scripts/meta_review.py
```

各detector環境は個別に同期できます。

```bash
uv sync --project detectors/pystylometry --locked
uv sync --project detectors/stylometric-ai-detector --locked
uv sync --project detectors/explain-ai-generated-text --locked
```

GitHub Actionsは各lockfileを再生成し、差分がある場合だけcommitします。

## Pages

静的UIは [`site/`](site/) にあります。

現在、コードとdeploy workflowは実装済みですが、repository側の**初回Pages site有効化だけ**GitHubの`GITHUB_TOKEN`では実行できませんでした。

一度だけ次を設定してください。

**Settings → Pages → Build and deployment → Source: GitHub Actions**

有効化後は `.github/workflows/pages.yml` が `site/` を自動deployします。

## コーパス方針

Zennを主要な観測対象候補にしますが、投稿本文をこのrepositoryへ再配布しません。Zenn利用規約では投稿者のコンテンツについて無断転載・二次配布を認めていないためです。

保存対象は原則として以下です。

- source URL
- published/fetched timestamp
- selection cohort
- SHA-256
- OSSが算出した派生統計量
- 再現に必要なprovenance

取得時だけ一時的に本文を処理し、公開artifactには本文を含めない設計にします。詳細は [`docs/CORPUS_POLICY.md`](docs/CORPUS_POLICY.md) を参照してください。

## 判定の意味

このサイトは「Claude製」「AI製」などを断定するwatermark detectorではありません。

表示するのは、公開OSSが算出した文章統計と、実測済み年次baselineとの距離です。年代差、媒体差、著者差、ジャンル差、編集、翻訳などでも分布は変化します。英語中心で設計されたdetectorを日本語へ適用する場合は、その一般化を保証せず参考値として扱います。

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
- [x] OSSメタレビューを正準化
- [x] 3 detectorを独立`uv.lock`で固定
- [x] Pages UIをWeb Worker + Pyodideへ分離
- [x] `pystylometry` canonical Python関数をWASMで実行
- [x] WASM compatibility smoke testをActions化
- [x] baseline未構築時をfail-closed化
- [ ] GitHub Pagesをrepository設定で初回有効化
- [ ] 2022–2026 corpusを固定
- [ ] 年次baselineを実測生成
- [ ] Pagesで年代距離を有効化
