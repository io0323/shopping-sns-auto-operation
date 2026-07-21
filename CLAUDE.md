# CLAUDE.md — Shopping SNS Auto Operation

## プロジェクト概要

楽天ROOM運用の半自動化システム。楽天APIで商品を収集・スコアリングし、LLMで投稿コンテンツを生成・品質評価する。**投稿操作は必ず人間が行う**(楽天ROOMに投稿APIは存在せず、UI自動化は規約違反のため)。

設計書は `docs/` を必ず参照すること:
- docs/01_要件定義.md
- docs/02_基本設計.md
- docs/03_詳細設計.md

## 技術スタック

- Backend: Python 3.12 / FastAPI / SQLAlchemy 2.x / APScheduler / Pydantic v2
- DB: SQLite(SQLAlchemy経由。PostgreSQL移行可能な書き方をする)
- Frontend: Next.js 15 (App Router) / TypeScript / Tailwind
- LLM: Anthropic SDK(モデル名は環境変数で切替。ハードコード禁止)
- パッケージ管理: uv(backend)/ npm(frontend)

## 絶対ルール

1. 楽天ROOM・楽天アフィリエイト管理画面へのスクレイピング/自動操作コードを書かない
2. APIキーをコードにハードコードしない。`.env` + `core/config.py` 経由のみ
3. 楽天APIリクエスト間は1.1秒以上のウェイト。429は指数バックオフ
4. LLM呼び出しは必ず `clients/llm.py` を経由し、llm_usageにトークン数を記録する
5. 再生成ループは最大3回。無限ループになる構造を作らない
6. プロンプトは `prompts/` のテキストファイルで管理。コード内に埋め込まない
7. スコア計算・禁止表現チェック・CSV突合には必ず単体テストを書く

## コーディング規約

- 不要なコメントを書かない。自明なdocstringも不要
- 型ヒント必須。mypy strictで通る書き方
- APIレスポンスは詳細設計のエラー仕様(`{"error": {"code", "message"}}`)に従う
- テーブル・API追加時は docs/03_詳細設計.md との整合を保つ(乖離する場合は設計書も更新)
- 確認質問はせず、設計書に基づいて実装を進める。設計書に無い判断はコミットメッセージに記載

## コマンド

```
backend:  cd backend && uv run uvicorn app.main:app --reload
test:     cd backend && uv run pytest
frontend: cd frontend && npm run dev
lint:     cd backend && uv run ruff check . && uv run mypy app
```

## 実装フェーズ

- Phase 1: 基盤 + Research/Selection/Generator/Evaluator + 日次パイプライン
- Phase 2: レビューUI + Export + CSVインポート + 分析ダッシュボード
- Phase 3: Learning Agent + プロンプト版管理 + 改善提案フロー

現在のフェーズと進捗は docs/PROGRESS.md に記録し、各フェーズ完了時に更新すること。
