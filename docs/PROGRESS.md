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

- 状態: 未着手

## Phase 2: レビューUI + Export + CSVインポート + 分析ダッシュボード

- 状態: 未着手

## Phase 3: Learning Agent + プロンプト版管理 + 改善提案フロー

- 状態: 未着手
