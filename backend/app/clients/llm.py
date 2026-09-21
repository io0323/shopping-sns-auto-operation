import logging
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from anthropic import Anthropic
from sqlalchemy.orm import Session

from app.clients.elf import require_llmops
from app.core.config import get_settings
from app.models import LlmUsage

if TYPE_CHECKING:
    from llmops.sdk import LLMOps

logger = logging.getLogger(__name__)

# 標準料金($/1Mトークン、2026-06-24時点)。プロモーション価格は変動するため
# 恒久的な標準単価を採用する。モデル追加時はここに追記すること。
PRICING_USD_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

#: Agent → ELF の論理モデル名。実モデル名は ELF 側で環境変数から解決する
ELF_LOGICAL_MODELS: dict[str, str] = {
    "generator": "harness-generator",
    "evaluator": "harness-evaluator",
    "learning": "harness-learning",
}


class RegisteredPrompt(str):
    """ELF の Prompt Registry に登録された Prompt をレンダリングした本文。

    文字列としては Harness が組み立てた本文そのもの(従来どおり扱える)。
    加えて ELF の prompt_id と変数を持ち、LlmClient はそれで ELF 経由の呼び出しを行う。
    ELF 側のレンダリング結果と本文がバイト一致しなければ、LLM を呼ぶ前に止まる
    (prompt_versions で activate された版が ELF に未登録、など)。
    """

    prompt_id: str
    variables: dict[str, Any]

    def __new__(
        cls, text: str, *, prompt_id: str, variables: Mapping[str, Any]
    ) -> "RegisteredPrompt":
        obj = super().__new__(cls, text)
        obj.prompt_id = prompt_id
        obj.variables = dict(variables)
        return obj


class UnregisteredPromptError(ValueError):
    """ELF に登録されていない Prompt を送ろうとした。"""


@dataclass
class LlmResult:
    text: str
    input_tokens: int
    output_tokens: int
    estimated_cost_jpy: float


def estimate_cost_jpy(
    model: str, input_tokens: int, output_tokens: int, usd_jpy_rate: float
) -> float:
    input_price, output_price = PRICING_USD_PER_MILLION_TOKENS.get(model, (0.0, 0.0))
    cost_usd = (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
    return cost_usd * usd_jpy_rate


def _response_text(raw: Mapping[str, Any], fallback: str) -> str:
    """SDK 応答の text ブロックを連結する(ELF 経由前と同じ取り出し方)。

    ELF の結果 text はコードフェンス除去済みのため使わない。
    応答の解釈は従来どおり各 Agent(strip_code_fence)に任せる。
    """
    blocks = raw.get("content")
    if not isinstance(blocks, list):
        return fallback
    return "".join(
        str(block.get("text", ""))
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    )


class LlmClient:
    """Agent の LLM 呼び出し口。ELF の Gateway を経由する。

    - span(Prompt 版・トークン・コスト)は ELF に記録される
    - LlmUsage は従来どおり Harness の DB に記録する(cost_guard が参照するため)
    - 再試行はしない(従来どおり1回。有料APIの呼び出し回数を増やさない)
    """

    def __init__(
        self,
        session: Session,
        client: Anthropic | None = None,
        ops: "LLMOps | None" = None,
    ) -> None:
        from llmops.adapters import AnthropicSdkAdapter

        settings = get_settings()
        self._session = session
        self._usd_jpy_rate = settings.usd_jpy_rate
        self._ops = ops or require_llmops()
        # API キーは Harness の Settings(.env)から。ELF は API キーの在り処を持たない
        sdk_client = client or Anthropic(api_key=settings.anthropic_api_key)
        self._ops.runtime.gateway.use_adapter(AnthropicSdkAdapter(sdk_client))

    def _prepare_model(self, agent: str, model: str, max_tokens: int) -> str:
        """論理モデルを決め、実モデル名(Harness の Settings)を ELF が読む環境変数へ渡す。"""
        logical_model = ELF_LOGICAL_MODELS[agent]
        params = self._ops.runtime.models.resolve(logical_model).params
        env_name = params.get("model_env")
        if env_name:
            os.environ[str(env_name)] = model
        if params.get("max_tokens") != max_tokens:
            logger.warning(
                "max_tokens が ELF の %s と一致しません(呼び出し=%s / models.yaml=%s)。"
                "models.yaml の値で呼び出します",
                logical_model,
                max_tokens,
                params.get("max_tokens"),
            )
        return logical_model

    def complete(
        self,
        *,
        job_id: uuid.UUID,
        agent: str,
        model: str,
        prompt: str,
        max_tokens: int = 1024,
    ) -> LlmResult:
        if not isinstance(prompt, RegisteredPrompt):
            raise UnregisteredPromptError(
                f"agent={agent}: ELF に登録された Prompt(RegisteredPrompt)以外は送れません"
            )
        logical_model = self._prepare_model(agent, model, max_tokens)

        result = self._ops.complete(
            prompt_id=prompt.prompt_id,
            variables=prompt.variables,
            model=logical_model,
            task=agent,
            retry=False,
            expected_text=str(prompt),
            meta={"job_id": str(job_id), "agent": agent},
        )

        text = _response_text(result.raw, result.text)
        input_tokens = result.input_tokens or 0
        output_tokens = result.output_tokens or 0
        cost = estimate_cost_jpy(model, input_tokens, output_tokens, self._usd_jpy_rate)

        self._session.add(
            LlmUsage(
                job_id=job_id,
                agent=agent,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_jpy=cost,
            )
        )
        self._session.flush()

        return LlmResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_jpy=cost,
        )
