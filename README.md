# detective

公開OSSを同一条件で継続比較し、文章の時系列分布変化を観測するメタレビュー基盤です。

## 目的

- 2022–2026 の公開技術文章コーパスを年次で固定する
- 既存の stylometry / AI-text detection OSS を `uv` で再現可能に管理する
- 自前の detector を主役にせず、OSSごとの出力・前提・限界を横並びで監査する
- GitHub Pages に「テキストを貼るだけ」の簡易判定UIを公開する
- 年代baselineが未構築・不十分な場合は推定を返さず fail-closed にする

## アーキテクチャ

```text
public corpus / benchmark data
        ↓
OSS adapters (uv locked)
        ↓
raw runs / metadata / provenance
        ↓
yearly baseline artifacts
        ↓
GitHub Pages
  └─ quick checker / meta review
```

`detective` 自体では新規のAI/Human分類モデルを開発しません。研究対象は既存OSSと文章分布の経年変化です。

## 初期比較対象

- `pystylometry` — stylometry指標群
- `stylometric-ai-detector` — 表層stylometry + Random Forestの公開baseline
- `explain-ai-generated-text` — 40+ linguistic features + SHAP / XGBoost / Random Forest

各パッケージのバージョンと根拠URLは [`detectors.toml`](detectors.toml) に固定します。

## 再現性

依存管理は `uv` を正準とします。

```bash
uv sync --locked
uv run --locked python scripts/meta_review.py
```

`pyproject.toml` が変わると GitHub Actions が `uv.lock` を再生成してcommitします。比較runでは `--locked` を使い、環境差による暗黙の更新を拒否します。

## Pages

静的UIは [`site/`](site/) にあります。Pages workflowはGitHub公式の `configure-pages` / `upload-pages-artifact` / `deploy-pages` を使います。

GitHub側で最初に一度だけ **Settings → Pages → Source: GitHub Actions** を有効化する必要があります。

## 判定の意味

このサイトは「Claude製」「AI製」などを断定するためのwatermark detectorではありません。表示するのは、公開OSSの参考スコア、文章統計、そして実測済み年次baselineとの距離です。OSSが英語中心の学習データを使う場合、日本語への一般化は保証されないため、その制約をUIに明示します。

## 証拠・一次情報

- GitHub Pages custom workflow: https://docs.github.com/en/enterprise-cloud@latest/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- uv project / dependency management: https://docs.astral.sh/uv/guides/projects/
- uv locking and `--locked`: https://docs.astral.sh/uv/concepts/projects/sync/
- pystylometry: https://pypi.org/project/pystylometry/
- stylometric-ai-detector 0.2.4: https://pypi.org/project/stylometric-ai-detector/0.2.4/
- explain-ai-generated-text: https://pypi.org/project/explain-ai-generated-text/

## Status

- [x] 空repoから開始
- [x] OSSメタレビューを正準にする
- [x] Pages UIを前提にする
- [ ] 2022–2026 corpusを固定
- [ ] 年次baselineを実測生成
- [ ] Pagesで年代距離を有効化
