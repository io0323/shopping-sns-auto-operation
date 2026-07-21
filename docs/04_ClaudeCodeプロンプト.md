# Claude Code プロンプト集 — Shopping SNS Auto Operation

使い方: プロジェクトルートに `CLAUDE.md` と `docs/`(設計書3点)を配置した状態で、Phase順に1プロンプトずつ実行する。各Phase完了後、動作確認してから次へ進む。

---

## Phase 0: プロジェクト初期化

```
docs/の設計書とCLAUDE.mdに従い、プロジェクト骨格を作成せよ。

- 詳細設計6章のディレクトリ構成を作成
- backend: uv初期化、FastAPI/SQLAlchemy/APScheduler/anthropic/pydantic-settings/pytest/ruff/mypy導入
- frontend: Next.js 15 + TypeScript + Tailwind初期化
- core/config.py: .env読込(RAKUTEN_APP_ID, RAKUTEN_AFFILIATE_ID, ANTHROPIC_API_KEY,
  MONTHLY_LLM_BUDGET_JPY, DATABASE_URL, MODEL_GENERATOR, MODEL_EVALUATOR)
- .env.example作成、.gitignoreに.envと*.dbを含める
- core/logging.py: JSON Lines形式、90日ローテーション
- GET /api/v1/health 実装
- docs/PROGRESS.md作成
完了条件: uvicorn起動とhealth応答、pytest・ruff・mypyが空振りで成功
```

## Phase 1-1: DBモデルと楽天APIクライアント

```
詳細設計1章の全テーブル(products, product_metrics, candidates, contents, results,
jobs, llm_usage, prompt_versions, import_errors)をSQLAlchemyモデルとして実装せよ。
Alembicでマイグレーション管理する。

clients/rakuten_api.py:
- 楽天市場ランキングAPI(IchibaItem/Ranking)とIchibaItem/Searchのクライアント
- リクエスト間1.1秒ウェイト、429/5xxは指数バックオフ(1s→4s→16s、3回)
- affiliateIdをパラメータに含めアフィリエイトURLを取得
- レスポンスはPydanticモデルにパース
テスト: レート制限ウェイト・バックオフ・パースをモックで検証
```

## Phase 1-2: Research / Selection Agent

```
agents/research.py:
- config/strategy.yamlのジャンルIDリストを読み、ジャンル別ランキング上位30件を取得
- products upsert(item_codeキー)、product_metricsに当日スナップショットinsert
- 同日再実行は上書き(冪等)

agents/selection.py:
- 詳細設計3章のスコア計算式を実装。重みはconfig/scoring.yaml(合計1.0をバリデーション)
- 除外条件: excluded=true / 直近30日にposted済み / メトリクス2日分未満
- 上位10件をcandidatesにscore_breakdown付きで登録

config/strategy.yaml, scoring.yaml, seasonality.yamlのサンプルを作成。
テスト: スコア計算の各要素と正規化、除外条件を固定データで検証
```

## Phase 1-3: LLMクライアントとGenerator / Evaluator Agent

```
clients/llm.py:
- Anthropic SDKラッパー。呼出ごとにllm_usageへモデル・トークン数・概算費用(円)を記録
- harness/cost_guard.py: 月間累計がMONTHLY_LLM_BUDGET_JPY超過ならBudgetExceededError

prompts/generator/gen-v1.txt, prompts/evaluator/eval-v1.txt を詳細設計4章の内容で作成し、
prompt_versionsに初期投入するseedスクリプトを用意。

agents/generator.py: 商品情報を埋め込んで生成、JSONパース(コードフェンス除去含む)、
文字数制約をコード側でも検証。

agents/evaluator.py:
1. config/ng_words.yamlによるルールチェック(正規表現対応)
2. LLM評価(5軸100点)
3. 詳細設計4.3の再生成ループ(最大3回、80点未満は改善指示を次回generatorに渡す)
4. 3回失敗はstatus=needs_review

テスト: ルールチェック(禁止語・#ad欠落・文字数超過)、再生成ループの回数上限、
コストガード発動をモックで検証
```

## Phase 1-4: Harness Engineと日次パイプライン

```
harness/pipeline.py, job_queue.py:
- daily_pipeline: research → selection → generate → evaluate → save → notify
- 各ステップの状態をjobsに永続化、失敗ステップからの再開に対応
- パイプラインIDによる二重起動防止(起動済みは409相当)
- 商品単位の失敗は記録して継続(全体を止めない)
- APSchedulerで毎日05:00起動 + POST /api/v1/pipelines/daily/run で手動起動
- 完了/失敗/コスト警告をログ通知(Slack Webhookは環境変数があれば送信)

Phase 1完了条件: 手動起動で「候補10件が生成・評価済みでDBに保存される」ことを
実APIキーなしのモックE2Eテストで確認できる
```

## Phase 2-1: REST APIとレビューUI

```
詳細設計2章のAPIを実装せよ(learning-report以外)。
ページング・エラーレスポンス共通仕様・operation log記録を含む。

frontend:
- /candidates: 当日候補一覧(スコア内訳をツールチップ表示)
- /review: evaluated/needs_review一覧。本文編集(PATCH時にedited_by_human記録)、
  承認/除外ボタン、品質スコア内訳表示
- /queue: 承認済みキュー。ROOM用/X用テキストのワンタップコピー、投稿完了マーク、
  scheduled_at順ソート
- UIはlocalhost前提。日本語表示
```

## Phase 2-2: Export AgentとCSVインポート

```
agents/export.py: 承認済みコンテンツをROOM用/X用に整形(ハッシュタグ結合、#ad確認、
投稿チェックリスト付き)。GET /export/queueで返却。

agents/importer.py + POST /import/affiliate-csv:
- Shift-JIS→UTF-8変換、楽天アフィリエイトレポートのカラムマッピング
- itemCode/URLでproducts突合、期間重複は上書き、突合不能行はimport_errorsへ
- レスポンスで取込件数・上書き件数・エラー件数を返す
- frontend /import: アップロードUIとエラー行表示

frontend /analytics: GET /analytics/summaryのKPI表示(clicks/conversions/revenue、
ジャンル別、期間指定)。/dashboard: 本日の候補数・要確認数・月間コスト・KPIサマリ。
テスト: 文字コード変換・突合・重複上書きを実CSVサンプルで検証
```

## Phase 3: Learning Agent

```
agents/learning.py:
- results×contents×candidatesを突合し、高成果群/低成果群の特徴比較
  (ジャンル、description長、ハッシュタグ、品質スコア軸、edited_by_human)
- 実績30件未満は「データ蓄積中」レポートのみ生成して終了
- LLMで週次レポートとプロンプト改善案を生成、prompt_versionsに
  status相当(is_active=false)で保存
- POST /prompts/{agent}/activateで人間が承認して初めて有効化
- weekly_pipeline(日曜06:00)に組込み
- frontend /analytics/learning: レポート閲覧と改善案の承認UI

プロンプトの自動有効化は実装しないこと。
```

---

## 補足: プロンプト運用のコツ

- 各プロンプトは新しいセッションで実行する(コンテキスト汚染防止)。CLAUDE.mdが設計書参照を強制する
- 実装が設計と乖離した場合は「docs/03_詳細設計.md の該当箇所も更新せよ」と追記して再実行
- Phase 1-3のLLM実呼び出し確認は少額で: `MONTHLY_LLM_BUDGET_JPY=100` にしてコストガードの動作確認も兼ねる
