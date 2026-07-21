import importlib.util
from pathlib import Path
from types import ModuleType

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, PromptVersion

SEED_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed_prompts.py"


def _load_seed_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_prompts", SEED_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_prompts_is_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    seed_prompts = _load_seed_module()
    seed_prompts.get_session_factory = lambda: factory  # type: ignore[attr-defined]

    seed_prompts.seed()
    seed_prompts.seed()

    with Session(engine) as session:
        rows = session.execute(select(PromptVersion)).scalars().all()
        agents = sorted(row.agent for row in rows)
        assert agents == ["evaluator", "generator"]
        for row in rows:
            assert row.is_active is True
            assert len(row.body) > 0
