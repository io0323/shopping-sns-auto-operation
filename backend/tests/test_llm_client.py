import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.clients.llm import LlmClient, estimate_cost_jpy
from app.models import Base, LlmUsage


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _fake_anthropic_response(
    text: str, input_tokens: int, output_tokens: int
) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def test_estimate_cost_jpy_known_model() -> None:
    cost = estimate_cost_jpy("claude-sonnet-5", 1_000_000, 1_000_000, usd_jpy_rate=150.0)
    assert cost == pytest.approx((3.00 + 15.00) * 150.0)


def test_estimate_cost_jpy_unknown_model_is_zero() -> None:
    assert estimate_cost_jpy("unknown-model", 1000, 1000, usd_jpy_rate=150.0) == 0.0


def test_llm_client_complete_records_usage_and_returns_result() -> None:
    session = _make_session()
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_anthropic_response(
        "hello world", input_tokens=100, output_tokens=50
    )

    llm_client = LlmClient(session, client=fake_client)
    job_id = uuid.uuid4()

    result = llm_client.complete(
        job_id=job_id, agent="generator", model="claude-sonnet-5", prompt="prompt text"
    )

    assert result.text == "hello world"
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    expected_cost = (100 / 1_000_000 * 3.00 + 50 / 1_000_000 * 15.00) * 150.0
    assert result.estimated_cost_jpy == pytest.approx(expected_cost)

    usage = session.execute(select(LlmUsage)).scalar_one()
    assert usage.job_id == job_id
    assert usage.agent == "generator"
    assert usage.model == "claude-sonnet-5"
    assert usage.input_tokens == 100
    assert usage.output_tokens == 50
    assert usage.estimated_cost_jpy == pytest.approx(expected_cost)

    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-5"
    assert call_kwargs["messages"] == [{"role": "user", "content": "prompt text"}]
