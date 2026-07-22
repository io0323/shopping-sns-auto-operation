import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.agents.evaluator import run_generate_and_evaluate
from app.clients.llm import LlmClient
from app.harness.cost_guard import BudgetExceededError, check_budget
from app.models import Candidate, Product

logger = logging.getLogger(__name__)


def generate_and_evaluate_candidates(
    session: Session,
    llm_client: LlmClient,
    job_id: uuid.UUID,
    candidates: list[Candidate],
) -> dict[str, Any]:
    generated = 0
    needs_review = 0
    failed = 0
    budget_exceeded = False

    for candidate in candidates:
        try:
            check_budget(session)
        except BudgetExceededError:
            budget_exceeded = True
            logger.warning("月間LLM予算を超過したため以降の生成を停止します")
            break

        product = session.get(Product, candidate.product_id)
        if product is None:
            failed += 1
            continue

        try:
            content = run_generate_and_evaluate(session, llm_client, job_id, product, candidate)
        except Exception:
            logger.exception("candidate generation failed: candidate_id=%s", candidate.id)
            failed += 1
            continue

        candidate.status = "generated"
        session.add(candidate)
        session.commit()

        if content.status == "evaluated":
            generated += 1
        else:
            needs_review += 1

    return {
        "candidates": len(candidates),
        "generated": generated,
        "needs_review": needs_review,
        "failed": failed,
        "budget_exceeded": budget_exceeded,
    }
