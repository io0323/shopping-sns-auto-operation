# 進捗

## Phase 0: プロジェクト初期化

- 状態: 完了(2026-07-21)
- 実施内容:
  - 詳細設計6章に沿ったディレクトリ構成を作成(backend/app/{api,agents,harness,clients,models,schemas,core}, backend/config, backend/prompts, backend/tests)
  - backend: uv初期化(Python 3.12固定)。FastAPI / SQLAlchemy 2.x / APScheduler / anthropic / pydantic-settings を導入。dev依存にpytest / ruff / mypy(strict) / httpx
  - frontend: Next.js 15(App Router / TypeScript / Tailwind / src/構成)を `create-next-app` で初期化
  - `core/config.py`: pydantic-settingsでリポジトリルートの `.env` を読み込み(RAKUTEN_APP_ID, RAKUTEN_AFFILIATE_ID, ANTHROPIC_API_KEY, MONTHLY_LLM_BUDGET_JPY, DATABASE_URL, MODEL_GENERATOR, MODEL_EVALUATOR)
  - `core/logging.py`: JSON Lines形式、`TimedRotatingFileHandler`で90日ローテーション(`backend/logs/app.jsonl`)
  - `GET /api/v1/health` 実装、共通エラーレスポンス `{"error": {"code", "message"}}` の例外ハンドラを追加
  - ルート `.env.example` / `.gitignore`(`.env`, `*.db`含む)を作成
- 完了条件の確認:
  - `uv run pytest` → 1 passed
  - `uv run ruff check .` → All checks passed
  - `uv run mypy app` → Success: no issues found
  - `uv run uvicorn app.main:app` 起動後、`GET /api/v1/health` が `{"status": "ok"}` を返すことを確認
  - `npm run build`(frontend)がエラーなく完了することを確認

## Phase 1: 基盤 + Research/Selection/Generator/Evaluator + 日次パイプライン

- 状態: 完了(2026-07-21)
- Phase 1-1 実施内容:
  - 詳細設計1章の全9テーブル(products, product_metrics, candidates, contents, results, jobs, llm_usage, prompt_versions, import_errors)をSQLAlchemy 2.0 Mappedスタイルで実装(`app/models/`)。UUID主キーは`Uuid(as_uuid=True)`、JSON列はPostgreSQL移行を見据え`JSON`型を使用
  - Alembicを導入し、`alembic/env.py`は`app.core.config.Settings`経由でDATABASE_URLを取得(ハードコード禁止ルールに準拠)。初期マイグレーション(`init tables`)を作成し、upgrade/downgrade双方を確認
  - `app/core/db.py`: engine/sessionmakerのシングルトン管理を追加(Alembicおよび今後のagentsから利用)
  - `clients/rakuten_api.py`: IchibaItem Ranking(20220601)/Search(20260701) APIクライアント。エンドポイント・レスポンス構造(`{"items": [{"item": {...}}]}`)は楽天ウェブサービス公式ドキュメントを直接確認して実装
    - リクエスト間1.1秒ウェイト、429/5xxは指数バックオフ(1s→4s→16s、3回)でリトライ、それ以外のエラーは即例外
    - レスポンスをPydanticモデル(`RakutenItem`)にパース。genreIdは`coerce_numbers_to_str`でDBのVARCHAR列と型を揃えた
  - テスト: レート制限ウェイト・バックオフ・パースをモックで検証(`tests/test_rakuten_api.py`)、SQLAlchemyモデルの永続化・リレーションを検証(`tests/test_models.py`)
- 設計書に無い判断:
  - `import_errors`テーブルのモデルクラス名は`ImportErrorRecord`(Python組み込み`ImportError`との衝突を避けるため)
  - `llm_usage.job_id`は設計書の型表記(UUID、NULLABLE指定なし)に従いNOT NULLとした
  - Rakuten APIエンドポイントは現行バージョン(Search: 20260701 / Ranking: 20220601)を採用。将来的にバージョンが変わった場合は`app/clients/rakuten_api.py`の定数を更新すること
- Phase 1-2 実施内容(2026-07-21):
  - `agents/research.py`: `config/strategy.yaml`のジャンルリストを読み、ジャンル別ランキング上位30件を取得。`item_code`でproductsをupsert、`(product_id, snapshot_date)`でproduct_metricsをupsert(同日再実行は上書きで冪等)。ジャンル単位のAPI失敗はそのジャンルをスキップして継続(基本設計5章のエラーハンドリング方針に準拠)
  - `agents/selection.py`: 詳細設計3章のスコア計算式(`rank_trend/review_growth/rating/seasonality/price_fit/competition`)を実装。重みは`config/scoring.yaml`から読み込み、絶対値合計が1.0であることをPydanticバリデータで検証。除外条件(`excluded=true` / 直近30日投稿済み / 直近7日メトリクス2日未満)を適用し、スコア上位N件(既定10、`strategy.yaml`の`daily_candidate_count`)を`score_breakdown`付きでcandidatesに登録
  - `config/strategy.yaml` / `config/scoring.yaml` / `config/seasonality.yaml` のサンプルを作成
  - テスト: スコア各要素の正規化・クリッピング、重み合計バリデーション、季節性フォールバック、除外条件、Top-N選定を固定データで検証(`tests/test_selection.py`)。research の upsert冪等性・ジャンル失敗時のスキップ継続を検証(`tests/test_research.py`)
- Phase 1-2 設計書に無い判断:
  - `config/strategy.yaml`の`genres`は「ID一覧」ではなく`{id, name}`のペア一覧とした。楽天Ranking/Search APIのレスポンスにはジャンル名(genreName)が含まれず、products.genre_name(NOT NULL)を埋める情報源が他に無いため。実運用では楽天ジャンル検索API(GenreSearch)で確認した名称に置き換える運用とする
  - price_fit(価格帯適合)の台形メンバーシップ関数は、詳細設計に明記のない外側の減衰境界(`soft_min`/`soft_max`)を`config/strategy.yaml`の`price_band`に追加して定義した(既定 500円/15,000円)
  - rank_trendは、比較対象の順位(7日前 or 当日)のいずれかが圏外(NULL)の場合は算出不能として0(中立)を返す仕様とした
  - 季節性係数は`config/seasonality.yaml`にジャンル×月の値が無い場合、`default`(既定0.5)にフォールバックする
- Phase 1-3 実施内容(2026-07-21):
  - `clients/llm.py`: Anthropic SDKラッパー(`LlmClient.complete`)。呼出ごとにllm_usageへモデル・トークン数・概算費用(円)を記録。料金は`claude-api`スキルで確認した標準単価($/1Mトークン: sonnet-5 3.00/15.00、haiku-4.5 1.00/5.00)を`USD_JPY_RATE`(既定150円、.env設定可)で円換算
  - `harness/cost_guard.py`: `check_budget`が当月累計(llm_usage.estimated_cost_jpyの月初からの合計)が`MONTHLY_LLM_BUDGET_JPY`以上なら`BudgetExceededError`を送出
  - `prompts/generator/gen-v1.txt` / `prompts/evaluator/eval-v1.txt` を詳細設計4章の内容で作成。`scripts/seed_prompts.py`でprompt_versionsに初期投入(`(agent, version)`単位で冪等)
  - `config/ng_words.yaml`: 詳細設計4.4の禁止表現辞書(断定・誇大/薬機法系/価格系)を正規表現として定義
  - `agents/generator.py`: `product_json`を埋め込みプロンプトをレンダリング、LLM呼出後にコードフェンス除去込みでJSONパース、文字数制約(title/description/hashtags個数/x_post/cta)をコード側で検証する`validate_length_constraints`を実装
  - `agents/evaluator.py`: `rule_check`(禁止語・#ad有無・文字数制約)→ LLM評価(5軸100点)→ 詳細設計4.3の再生成ループ(最大3回、ルール違反時はLLM評価を呼ばず即再生成、80点未満は`improvement`を次回`generator`に渡す)→ 3回失敗で`status=needs_review`、成功で`status=evaluated`
  - テスト: ルールチェック(禁止語/#ad欠落/文字数超過)、再生成ループの回数上限とルール違反時の評価スキップ、コストガード発動をモック・固定データで検証(`tests/test_generator.py`, `tests/test_evaluator.py`, `tests/test_llm_client.py`, `tests/test_cost_guard.py`, `tests/test_seed_prompts.py`)
- Phase 1-3 設計書に無い判断:
  - LLMコストのUSD→JPY換算レートは設計書に定義が無いため、`USD_JPY_RATE`(既定150、.envで上書き可)を新設
  - モデル料金は変動するプロモーション価格ではなく恒久的な標準単価を採用(`clients/llm.py`のコメントに出典日時を明記)。`MODEL_EVALUATOR`の既定値をpricing表のキーと一致させるため`claude-haiku-4-5`(日付なしエイリアス)に統一
  - Content.regen_countは「何回目の試行で確定したか」(0始まり)を記録する仕様とした
  - cost_guard.check_budgetの呼び出し箇所(パイプライン停止の実配線)はharness/pipeline.py実装時(Phase1-4)に行う。本フェーズでは関数として提供のみ
- Phase 1-4 実施内容(2026-07-21):
  - `harness/job_queue.py`: `jobs`テーブルを使ったステップ状態管理のプリミティブ。`is_pipeline_running`(pipeline単位の二重起動チェック)、`start_step`/`finish_step`(状態遷移・エラー記録)、`get_step_job`(payload内の`run_date`で当日分のステップを特定し、`status=done`ならスキップして再開できるようにする)
  - `harness/pipeline.py`: `run_daily_pipeline`で research → selection → generate(候補ごとにEvaluator込みで生成、商品単位の例外はログして`continue`し全体を止めない) → save(保存結果の集計) → notify(ログ+Slack Webhook)を順に実行。各ステップの実行前に`jobs`の完了状態を確認し、完了済みステップは再実行せずスキップ(失敗ステップからの再開に対応)。呼出時点で当該pipelineが`pending`/`running`のjobを持てば`PipelineAlreadyRunningError`を送出(二重起動防止)。generateステップでは候補ごとにLLM呼出前に`cost_guard.check_budget`を確認し、超過時はそれ以降の生成を停止しつつ(候補は`needs_review`化せず未処理のまま)save/notifyへ進む。`create_scheduler()`でAPScheduler(`AsyncIOScheduler`)の毎日05:00 cronジョブを定義
  - `POST /api/v1/pipelines/daily/run`(`api/pipelines.py`): `run_daily_pipeline`を同期実行し、二重起動時は`PipelineAlreadyRunningError`を409(`{"error":{"code":"CONFLICT",...}}`)に変換
  - `main.py`: FastAPIの`lifespan`でAPSchedulerを起動/終了するよう配線(`app/harness/pipeline.create_scheduler`)
  - Phase1-3で発見した`agents/evaluator.py`の不具合を修正: LLM評価が80点未満の場合に`improvement_hint`を更新する行が欠落しており再生成のたびに同じ内容を生成し続けていた(詳細設計4.3の「改善指示を次回Generatorに渡す」が機能していなかった)。あわせて末尾の到達不能な重複コードを削除
  - テスト: `run_daily_pipeline`の手動起動で候補10件が生成・評価済みでDBに保存されること(実APIキー不要のモックE2E、Phase1完了条件)、二重起動時の例外、失敗/未実行ステップからの再開(完了済みステップはRakuten API呼び出しなしでスキップ)、コストガード発動時の生成停止とnotifyへの継続、job_queueの状態遷移、Slack通知の送信/未設定時のスキップ/例外握りつぶしを検証(`tests/test_pipeline.py`, `tests/test_job_queue.py`, `tests/test_pipeline_notify.py`)。あわせてevaluator.pyの改善指示が次回生成プロンプトに反映されることを検証する回帰テストを追加(`tests/test_evaluator.py`)
- Phase 1-4 設計書に無い判断:
  - `jobs`テーブルに実行日(run_date)を区別するカラムが無いため、`payload`(JSON)に`{"run_date": "YYYY-MM-DD"}`を格納し、当日分のステップ状態の特定・再開判定に利用する
  - 「generate」「evaluate」の2ステップは、Phase1-3で実装済みの再生成ループ(Generator/Evaluatorを最大3回相互に呼び出す)の都合上、jobsテーブル上は単一の`generate`ステップとして記録する(内部でEvaluator呼び出しも行う)。`save`ステップは、既に`run_generate_and_evaluate`内で永続化済みのContentを集計・確認するチェックポイントとして実装した
  - パイプラインの二重起動防止は「パイプラインID」を新設カラムとして持たせるのではなく、`pipeline`(例: "daily")に対して未完了(`pending`/`running`)の`jobs`行が存在するかで判定する(スキーマ変更を避けるため)
  - Slack Webhook送信失敗(接続エラー等)はログに記録するのみでパイプライン自体は失敗させない
  - `SLACK_WEBHOOK_URL`を新設(任意、.env未設定なら通知は送信しない)
- 状態: 完了(2026-07-21)。Phase 1完了条件(手動起動で候補10件が生成・評価済みでDB保存されることをモックE2Eで確認)を満たした

## Phase 2: レビューUI + Export + CSVインポート + 分析ダッシュボード

- 状態: 進行中(2-1完了、2026-07-22)
- Phase 2-1 実施内容:
  - バックエンド(詳細設計2章、learning-report・POST /import/affiliate-csv・GET /export/queue・POST /prompts/{agent}/activateを除く。理由は下記「設計書に無い判断」参照):
    - `GET /products`(genre_id/min_score/excluded フィルタ、ページング)、`GET /products/{id}/metrics`
    - `GET /candidates?date=`(product情報+score_breakdown付き、スコア降順)
    - `POST /generate`(`{candidate_ids}` → 202 Accepted + `{job_id}`。FastAPI `BackgroundTasks`で`harness/generation.py`の共通処理を非同期実行)、`GET /jobs/{id}`(ポーリング用)
    - `GET /contents?status=`(複数指定可、sort許可リストによる並び替え)、`PATCH /contents/{id}`(本文編集時のみ`edited_by_human=true`を自動設定。scheduled_atのみの更新では立てない)、`POST /contents/{id}/approve` / `/reject` / `/mark-posted`(posted_at記録)
    - 共通仕様: ページング(`page`/`per_page`/`meta.total`)、エラーレスポンス`{"error":{"code","message"}}`(既存の例外ハンドラを流用)
    - 操作ログ: 新設した`operation_logs`テーブル(id, operation, target_type, target_id, detail, created_at)に承認・除外・投稿マーク・編集を記録する`core/operation_log.py`の`record_operation`を追加
    - `harness/generation.py`: Phase1-4の`harness/pipeline.py`から候補ごとの生成+評価ループ(Cost Guard確認・商品単位の例外継続)を切り出し、日次パイプラインと手動`POST /generate`の両方から共有
    - CORS: フロントエンド(`http://localhost:3000`)からの呼び出しを許可する`CORSMiddleware`を追加
  - フロントエンド(Next.js App Router、日本語表示、`NEXT_PUBLIC_API_BASE_URL`未設定時は`http://localhost:8000`を既定):
    - `/candidates`: 当日候補一覧。スコアにマウスホバーすると`score_breakdown`をツールチップ表示(日本語ラベル変換)
    - `/review`: `evaluated`/`needs_review`一覧。タイトル・説明文・ハッシュタグ・X投稿文・CTAを編集して保存(PATCH)、品質スコア内訳表示、承認/除外ボタン
    - `/queue`: `approved`一覧を`scheduled_at`昇順で表示。ROOM用(タイトル+説明文+ハッシュタグ)/X用テキストをワンタップコピー(Clipboard API)、投稿完了マークボタン
    - 共通の`lib/api.ts`(型付きfetchラッパー、`ApiError`)、`components/NavBar.tsx`
  - テスト: `tests/conftest.py`でAPI用のin-memory SQLiteフィクスチャ(バックグラウンドタスクからの独立セッションも同じ接続を共有するようcore/dbのモジュールグローバルを差し替え)を新設。products/candidates/contents(一覧・フィルタ・ソート不正値・PATCH・承認・除外・投稿マーク・操作ログ記録)/generate(202→ジョブ完了→Content生成の一連)を検証(`tests/test_api_*.py`)
  - 検証: `uv run pytest`(91 passed)、`uv run ruff check .`、`uv run mypy app`。フロントエンドは`npm run build`/`npm run lint`に加え、実際にbackend(移行済みDBにシードデータ投入)とfrontend devサーバーを起動し、各ページのSSRシェル・CORSヘッダー・PATCH/approve/mark-postedの実APIフローをcurlで確認(ブラウザでのクリック操作自体は自動化ツールが無いため未実施)
- Phase 2-1 設計書に無い判断:
  - `詳細設計2章のAPIを実装せよ(learning-report以外)`は文言通りには全API網羅を意味するが、`docs/04_ClaudeCodeプロンプト.md`のフェーズ別プロンプトでは`GET /export/queue`と`POST /import/affiliate-csv`はPhase2-2(`agents/export.py`/`agents/importer.py`)、`POST /prompts/{agent}/activate`はPhase3(Learning Agent)に明示的に割り当てられている。フェーズ別実行ガイドを優先し、これらとGET /analytics/summary・GET /costs(Phase2-2の/dashboard・/analytics向け)は今回スコープ外とした
  - `/queue`フロントエンドはPhase2-2で実装予定の`GET /export/queue`(ハッシュタグ整形・#ad確認・投稿チェックリスト付き)ではなく、既存の`GET /contents?status=approved`をそのまま使用し、ROOM用テキストはクライアント側で`title+description+hashtags`を組み立てて簡易的に生成した。Phase2-2でexport.py実装後に差し替える想定
  - 操作ログは詳細設計に表形式の記載はあるが専用テーブルが無いため、`operation_logs`テーブルを新設(Alembicマイグレーション追加)
  - PATCH /contents/{id}のedited_by_humanは、タイトル/説明文/ハッシュタグ/X投稿文/CTAのいずれかを変更した場合のみtrueにする(scheduled_atのみの変更では人間による本文修正とみなさない)
  - POST /generateの`job.pipeline`は詳細設計1章に例示されている`manual_generate`を採用

## Phase 3: Learning Agent + プロンプト版管理 + 改善提案フロー

- 状態: 未着手

## Phase 3: Learning Agent + プロンプト版管理 + 改善提案フロー

- 状態: 未着手
