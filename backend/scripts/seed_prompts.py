"""prompt_versions に初期プロンプト(gen-v1, eval-v1)を投入するseedスクリプト。

実行: cd backend && uv run python scripts/seed_prompts.py
同じ(agent, version)が既に存在する場合は本文を上書きするだけで、重複行は作らない(冪等)。
"""

from pathlib import Path

from sqlalchemy import select

from app.core.db import get_session_factory
from app.models import PromptVersion

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

SEED_PROMPTS = (
    ("generator", "gen-v1", PROMPTS_DIR / "generator" / "gen-v1.txt"),
    ("evaluator", "eval-v1", PROMPTS_DIR / "evaluator" / "eval-v1.txt"),
    ("learning", "learning-v1", PROMPTS_DIR / "learning" / "learning-v1.txt"),
)


def seed() -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        for agent, version, path in SEED_PROMPTS:
            body = path.read_text(encoding="utf-8")

            existing = session.execute(
                select(PromptVersion).where(
                    PromptVersion.agent == agent, PromptVersion.version == version
                )
            ).scalar_one_or_none()

            if existing is None:
                session.add(
                    PromptVersion(agent=agent, version=version, body=body, is_active=True)
                )
            else:
                existing.body = body
                existing.is_active = True

        session.commit()


if __name__ == "__main__":
    seed()
