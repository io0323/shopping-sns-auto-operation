import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.agents.generator import generator_variables, render_prompt
from app.clients.llm import (
    LlmClient,
    RegisteredPrompt,
    UnregisteredPromptError,
    estimate_cost_jpy,
)
from app.models import Base, LlmUsage, Product

GEN_V1 = Path(__file__).resolve().parents[1] / "prompts" / "generator" / "gen-v1.txt"


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


def _product() -> Product:
    return Product(name="テスト商品", genre_name="スイーツ", shop_name="ショップ")


def _generator_prompt(template: str, hint: str | None = None) -> RegisteredPrompt:
    product = _product()
    return RegisteredPrompt(
        render_prompt(template, product, hint),
        prompt_id="harness.generator",
        variables=generator_variables(product, hint),
    )


def test_estimate_cost_jpy_known_model() -> None:
    cost = estimate_cost_jpy("claude-sonnet-5", 1_000_000, 1_000_000, usd_jpy_rate=150.0)
    assert cost == pytest.approx((3.00 + 15.00) * 150.0)


def test_estimate_cost_jpy_unknown_model_is_zero() -> None:
    assert estimate_cost_jpy("unknown-model", 1000, 1000, usd_jpy_rate=150.0) == 0.0


def test_registered_prompt_behaves_as_the_rendered_text() -> None:
    """既存の呼び出し側(プロンプト書き出しAPI・テストの Fake)からは普通の文字列に見える。"""
    template = GEN_V1.read_text(encoding="utf-8")
    prompt = _generator_prompt(template)
    assert isinstance(prompt, str)
    assert str(prompt) == render_prompt(template, _product(), None)
    assert prompt.prompt_id == "harness.generator"


# ---------------------------------------------------------------------------
# ELF 経由の呼び出し(llmops がある環境のみ)
# ---------------------------------------------------------------------------


@pytest.fixture
def ops() -> Any:
    pytest.importorskip("llmops")
    from app.clients.elf import require_llmops

    return require_llmops()


def test_llm_client_complete_records_usage_and_returns_result(ops: Any) -> None:
    session = _make_session()
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_anthropic_response(
        "hello world", input_tokens=100, output_tokens=50
    )

    llm_client = LlmClient(session, client=fake_client, ops=ops)
    job_id = uuid.uuid4()
    prompt = _generator_prompt(GEN_V1.read_text(encoding="utf-8"))

    result = llm_client.complete(
        job_id=job_id, agent="generator", model="claude-sonnet-5", prompt=prompt
    )

    assert result.text == "hello world"
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    expected_cost = (100 / 1_000_000 * 3.00 + 50 / 1_000_000 * 15.00) * 150.0
    assert result.estimated_cost_jpy == pytest.approx(expected_cost)

    # cost_guard が参照する LlmUsage は従来どおり Harness の DB に残る
    usage = session.execute(select(LlmUsage)).scalar_one()
    assert usage.job_id == job_id
    assert usage.agent == "generator"
    assert usage.model == "claude-sonnet-5"
    assert usage.input_tokens == 100
    assert usage.output_tokens == 50
    assert usage.estimated_cost_jpy == pytest.approx(expected_cost)

    # SDK には Harness が組み立てた本文と、Settings の実モデル名がそのまま渡る
    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-5"
    assert call_kwargs["max_tokens"] == 1024
    assert call_kwargs["messages"] == [{"role": "user", "content": str(prompt)}]
    assert fake_client.messages.create.call_count == 1, "再試行しない(有料APIの回数を増やさない)"


def test_llm_client_records_a_span_in_elf(ops: Any) -> None:
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_anthropic_response("{}", 7, 3)
    llm_client = LlmClient(_make_session(), client=fake_client, ops=ops)

    with ops.trace("pipeline.daily") as tr:
        llm_client.complete(
            job_id=uuid.uuid4(),
            agent="generator",
            model="claude-sonnet-5",
            prompt=_generator_prompt(GEN_V1.read_text(encoding="utf-8"), hint="短すぎます"),
        )

    (span,) = ops.spans(tr.trace_id)
    assert span["prompt_id"] == "harness.generator"
    assert span["logical_model"] == "harness-generator"
    assert (span["input_tokens"], span["output_tokens"]) == (7, 3)
    assert span["cost_usd"] > 0, "有料APIのコストが ELF 側にも載る(予算判定の材料)"
    assert "claude-sonnet-5" not in (span["resolved_target"] or ""), "実モデル名は残さない"
    assert json.loads(span["meta_json"])["agent"] == "generator"


def test_response_text_is_not_fence_stripped(ops: Any) -> None:
    """応答の解釈(strip_code_fence)は従来どおり Agent 側。ELF で先に加工しない。"""
    fenced = '```json\n{"a": 1}\n```'
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_anthropic_response(fenced, 1, 1)
    llm_client = LlmClient(_make_session(), client=fake_client, ops=ops)

    result = llm_client.complete(
        job_id=uuid.uuid4(),
        agent="generator",
        model="claude-sonnet-5",
        prompt=_generator_prompt(GEN_V1.read_text(encoding="utf-8")),
    )
    assert result.text == fenced


def test_unregistered_prompt_is_refused(ops: Any) -> None:
    fake_client = MagicMock()
    llm_client = LlmClient(_make_session(), client=fake_client, ops=ops)

    with pytest.raises(UnregisteredPromptError):
        llm_client.complete(
            job_id=uuid.uuid4(), agent="generator", model="m", prompt="素の文字列"
        )
    fake_client.messages.create.assert_not_called()


def test_version_unknown_to_elf_is_refused_before_the_call(ops: Any) -> None:
    """prompt_versions で activate した版が ELF に未登録なら、API を呼ばずに止まる。

    Learning Agent の提案を人が activate しても、ELF の評価ゲートを通っていない版は
    本番で使わせない(ELF に登録 → 評価 → publish の順を強制する)。
    """
    from llmops.errors import PromptMismatch

    fake_client = MagicMock()
    session = _make_session()
    llm_client = LlmClient(session, client=fake_client, ops=ops)
    proposed_v2 = GEN_V1.read_text(encoding="utf-8").replace("コンテンツライター", "編集者")

    with pytest.raises(PromptMismatch):
        llm_client.complete(
            job_id=uuid.uuid4(),
            agent="generator",
            model="claude-sonnet-5",
            prompt=_generator_prompt(proposed_v2),
        )
    fake_client.messages.create.assert_not_called()
    assert session.execute(select(LlmUsage)).first() is None
