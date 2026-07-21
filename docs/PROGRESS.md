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
- 未着手: Phase 1-2(Research/Selection Agent)以降

## Phase 2: レビューUI + Export + CSVインポート + 分析ダッシュボード

- 状態: 未着手

## Phase 3: Learning Agent + プロンプト版管理 + 改善提案フロー

- 状態: 未着手
