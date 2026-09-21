import shutil
from collections.abc import Generator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.clients.elf as elf_module
import app.core.db as db_module
from app.main import app
from app.models import Base, Candidate, Content, Job, LlmUsage, Product, PromptVersion, Result


def _elf_config_lines(db: Path) -> list[str]:
    lines = ["system: harness", "paths:", f"  db: {db}"]
    try:
        from llmops.config import project_root
    except ImportError:
        return lines
    elf_root = project_root()
    return lines + [
        f"  prompts_dir: {elf_root / 'prompts'}",
        f"  models_file: {elf_root / 'models.yaml'}",
    ]


@pytest.fixture(scope="session")
def elf_template_db(tmp_path_factory: pytest.TempPathFactory) -> Path | None:
    """Prompt / 論理モデルを sync 済みの ELF DB(セッションで1回だけ作る)。"""
    try:
        from llmops.sdk import LLMOps
    except ImportError:
        return None
    root = tmp_path_factory.mktemp("elf-template")
    db = root / "elf.sqlite3"
    (root / "config.yaml").write_text(
        "\n".join(_elf_config_lines(db)) + "\n", encoding="utf-8"
    )
    ops = LLMOps.load(root / "config.yaml", system="harness")
    ops.runtime.prompts.sync()
    ops.runtime.models.sync()
    ops.close()
    return db


@pytest.fixture(autouse=True)
def isolated_elf(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    elf_template_db: Path | None,
) -> Generator[None, None, None]:
    """ELF(llmops)の記録先をテストごとの一時DBにする。本番の ELF DB を汚さない。

    Prompt と論理モデルは ELF リポジトリの実物(prompts/ と models.yaml)を読む。
    Harness の Prompt が ELF 登録版とバイト一致していることも、ここで一緒に検証される。
    llmops が未インストールの環境(CI)では ELF は使われないので、設定するだけで無害。
    """
    root = tmp_path_factory.mktemp("elf")
    db = root / "elf.sqlite3"
    if elf_template_db is not None:
        shutil.copyfile(elf_template_db, db)
    (root / "config.yaml").write_text("\n".join(_elf_config_lines(db)) + "\n", encoding="utf-8")
    monkeypatch.setenv("ELF_CONFIG", str(root / "config.yaml"))
    # LlmClient が実モデル名を書き込む環境変数。テスト後に元へ戻す
    for name in ("MODEL_GENERATOR", "MODEL_EVALUATOR", "MODEL_LEARNING"):
        monkeypatch.setenv(name, "")

    elf_module.reset_llmops()
    yield
    # 他スレッド(BackgroundTasks)が作ったハンドルは、そのスレッドの終了とともに捨てられる
    elf_module.reset_llmops()


@pytest.fixture
def db_session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    original_engine = db_module._engine
    original_factory = db_module._SessionLocal
    db_module._engine = engine
    db_module._SessionLocal = session_factory

    yield session_factory

    db_module._engine = original_engine
    db_module._SessionLocal = original_factory
    engine.dispose()


@pytest.fixture
def api_client(db_session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def make_product(session: Session, **overrides: Any) -> Product:
    defaults: dict[str, Any] = {
        "item_code": "shop1:0001",
        "name": "テスト商品",
        "genre_id": "100283",
        "genre_name": "スイーツ",
        "shop_code": "shop1",
        "shop_name": "ショップ",
        "item_url": "https://item.rakuten.co.jp/shop1/0001/",
    }
    defaults.update(overrides)
    product = Product(**defaults)
    session.add(product)
    session.commit()
    return product


def make_candidate(session: Session, product: Product, **overrides: Any) -> Candidate:
    defaults: dict[str, Any] = {
        "product_id": product.id,
        "selected_date": date(2026, 7, 22),
        "score": 0.8,
        "score_breakdown": {"rank_trend": 0.5},
        "status": "selected",
    }
    defaults.update(overrides)
    candidate = Candidate(**defaults)
    session.add(candidate)
    session.commit()
    return candidate


def make_content(
    session: Session, product: Product, candidate: Candidate, **overrides: Any
) -> Content:
    defaults: dict[str, Any] = {
        "product_id": product.id,
        "candidate_id": candidate.id,
        "title": "タイトル",
        "description": "あ" * 100,
        "hashtags": ["#a", "#b", "#c", "#d", "#e"],
        "x_post": "投稿テキスト #ad",
        "cta": "今すぐチェック",
        "prompt_version": "gen-v1",
        "status": "evaluated",
        "quality_score": 90.0,
        "quality_breakdown": {
            "natural": 18,
            "readability": 18,
            "appeal": 18,
            "uniqueness": 18,
            "compliance": 18,
        },
    }
    defaults.update(overrides)
    content = Content(**defaults)
    session.add(content)
    session.commit()
    return content


def make_result(session: Session, product: Product, **overrides: Any) -> Result:
    defaults: dict[str, Any] = {
        "product_id": product.id,
        "report_date_from": date(2026, 7, 1),
        "report_date_to": date(2026, 7, 7),
        "clicks": 10,
        "conversions": 1,
        "revenue": 500,
    }
    defaults.update(overrides)
    result = Result(**defaults)
    session.add(result)
    session.commit()
    return result


def make_job(session: Session, **overrides: Any) -> Job:
    defaults: dict[str, Any] = {"pipeline": "daily", "step": "generate", "status": "done"}
    defaults.update(overrides)
    job = Job(**defaults)
    session.add(job)
    session.commit()
    return job


def make_llm_usage(session: Session, job: Job, **overrides: Any) -> LlmUsage:
    defaults: dict[str, Any] = {
        "job_id": job.id,
        "agent": "generator",
        "model": "claude-sonnet-5",
        "input_tokens": 100,
        "output_tokens": 200,
        "estimated_cost_jpy": 1.5,
    }
    defaults.update(overrides)
    usage = LlmUsage(**defaults)
    session.add(usage)
    session.commit()
    return usage


def make_prompt_version(session: Session, **overrides: Any) -> PromptVersion:
    defaults: dict[str, Any] = {
        "agent": "generator",
        "version": "gen-v1",
        "body": "プロンプト本文",
        "is_active": True,
    }
    defaults.update(overrides)
    prompt_version = PromptVersion(**defaults)
    session.add(prompt_version)
    session.commit()
    return prompt_version
