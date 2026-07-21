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

- 状態: 進行中(1-1完了、2026-07-21)
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
- 未着手: Phase 1-4(Harness Engineと日次パイプライン)以降

## Phase 2: レビューUI + Export + CSVインポート + 分析ダッシュボード

- 状態: 未着手

## Phase 3: Learning Agent + プロンプト版管理 + 改善提案フロー

- 状態: 未着手
