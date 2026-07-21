import uuid
from dataclasses import dataclass

from anthropic import Anthropic
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import LlmUsage

# 標準料金($/1Mトークン、2026-06-24時点)。プロモーション価格は変動するため
# 恒久的な標準単価を採用する。モデル追加時はここに追記すること。
PRICING_USD_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


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


class LlmClient:
    def __init__(self, session: Session, client: Anthropic | None = None) -> None:
        settings = get_settings()
        self._session = session
        self._client = client or Anthropic(api_key=settings.anthropic_api_key)
        self._usd_jpy_rate = settings.usd_jpy_rate

    def complete(
        self,
        *,
        job_id: uuid.UUID,
        agent: str,
        model: str,
        prompt: str,
        max_tokens: int = 1024,
    ) -> LlmResult:
        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )

        text = "".join(block.text for block in response.content if block.type == "text")
        usage = response.usage
        cost = estimate_cost_jpy(model, usage.input_tokens, usage.output_tokens, self._usd_jpy_rate)

        self._session.add(
            LlmUsage(
                job_id=job_id,
                agent=agent,
                model=model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                estimated_cost_jpy=cost,
            )
        )
        self._session.flush()

        return LlmResult(
            text=text,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost_jpy=cost,
        )
