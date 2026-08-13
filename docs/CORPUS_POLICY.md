# Corpus Policy

`detective` は文章本文の再配布repositoryではなく、公開文章の**時系列分布を再現可能に観測するためのprovenance / derived-statistics repository**です。

## Zenn

### 利用条件

確認対象:

- 利用規約: https://zenn.dev/terms
- robots.txt: https://zenn.dev/robots.txt
- コミュニティガイドライン: https://zenn.dev/guideline

2026-08-13確認時点で、Zennの利用規約第6条は利用者コンテンツの著作権が投稿者または権利者に留保され、権利者の許可なく無断転載・二次配布できないとしています。

robots.txt は一般User-agentに `/search` をDisallowしており、サイトマップ `https://zenn.dev/sitemaps/_index.xml` を案内しています。

### detectiveで保存するもの

公開repositoryへ保存可能な正準recordは原則として次に限定します。

```json
{
  "source_url": "https://zenn.dev/.../articles/...",
  "published_at": "...",
  "fetched_at": "...",
  "year": 2026,
  "cohort": "...",
  "content_sha256": "...",
  "detector": "pystylometry==1.4.3",
  "metrics": {}
}
```

本文は取得処理の一時入力にのみ使用し、公開artifact / Git historyへ保存しません。

### 取得ルール

- `/search` はクロールしない
- 有料部分へのアクセス回避・認証回避をしない
- 公開状態で取得できる内容だけを扱う
- User-Agentを明示する
- 低頻度・逐次取得を基本とし、サイト運営を妨害するような並列大量取得をしない
- HTTP error / rate limit時はfail-closeし、強制retry loopを行わない
- 同一URLを不必要に再取得しない
- raw HTML / Markdownをrepositoryへcommitしない

## note

noteはZennと取得経路を共有しません。2026-08-13確認時点の `https://note.com/robots.txt` では、一般User-agentに `/api/*` と `/search` がDisallowされ、`https://note.com/sitemaps/production/note.com/sitemap.xml.gz` がSitemapとして案内されています。

そのためdetectiveのnote collectorは次を固定ルールとします。

- `/api/*` を収集に使わない
- `/search` を収集に使わない
- robots.txtが案内する公式sitemapだけを候補発見に使う
- 公開記事ページだけを低頻度で読む
- 本文は一時解析のみで、Git historyへ保存しない
- `top` はnote公式が同一基準のランキングとして公開した集合だけに使う
- それ以外の反応値上位集合は `high-engagement` と呼び、全noteのglobal TOPとは主張しない
- 2026年が未完年の間は、2022通年と2026通年を直接比較せず、同じ期間窓だけを比較する

noteのcohortはZenn baselineへ混ぜず、Pagesでも別系列として表示します。

## 年次比較のselection policy

年代差と人気度・著者・topic差を混同しないため、最低でも2 cohortを分離します。

### `temporal-reference`

年ごとの文章分布そのものを見るための固定sample。URL集合を一度freezeしたら、削除等の明確な理由がない限り都合よく差し替えません。

### `high-engagement`

公開されているengagement情報を取得できる場合のみ構築する補助cohort。engagement取得方法が公式に安定提供されていない場合は、主解析へ混ぜません。

### `official-ranked`

媒体運営者が順位・選出基準・集計期間を明示した集合。媒体間・年代間で基準が一致しない場合は同じランキング系列として比較しません。

## 年代推定の公開条件

`site/data/baselines.json` を `status = ready` に変更できるのは、次を満たした場合だけです。

1. 2022–2026の全年度に実sampleが存在する
2. 全recordにsource URL / fetched timestamp / SHA-256が存在する
3. sample countをUIへ表示できる
4. 使用OSSとversionを固定できる
5. cohort selection ruleを公開できる
6. baseline生成を同一manifestから再現できる

それまではPagesは年代推定を返さずfail-closedにします。

## 解釈

年次分布への距離はAI生成の証明ではありません。媒体、topic、著者層、文章長、編集方針、翻訳、テンプレート等のcovariateによっても変化します。
