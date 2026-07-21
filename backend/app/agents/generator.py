import json
import re
import uuid

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.llm import LlmClient
from app.core.config import get_settings
from app.models import Product, PromptVersion

TITLE_MAX = 30
DESCRIPTION_MIN = 80
DESCRIPTION_MAX = 150
HASHTAGS_MIN = 5
HASHTAGS_MAX = 8
X_POST_MAX = 120
CTA_MAX = 20

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class GeneratedContent(BaseModel):
    title: str
    description: str
    hashtags: list[str]
    x_post: str
    cta: str


def strip_code_fence(text: str) -> str:
    stripped = text.strip()
    match = _CODE_FENCE_RE.match(stripped)
    return match.group(1) if match else stripped


def parse_generated_content(text: str) -> GeneratedContent:
    raw = strip_code_fence(text)
    data = json.loads(raw)
    return GeneratedContent.model_validate(data)


def validate_length_constraints(content: GeneratedContent) -> list[str]:
    violations: list[str] = []
    if len(content.title) > TITLE_MAX:
        violations.append(f"title が{TITLE_MAX}文字を超過しています({len(content.title)}文字)")
    if not (DESCRIPTION_MIN <= len(content.description) <= DESCRIPTION_MAX):
        violations.append(
            f"description が{DESCRIPTION_MIN}〜{DESCRIPTION_MAX}文字の範囲外です"
            f"({len(content.description)}文字)"
        )
    if not (HASHTAGS_MIN <= len(content.hashtags) <= HASHTAGS_MAX):
        violations.append(
            f"hashtags が{HASHTAGS_MIN}〜{HASHTAGS_MAX}個の範囲外です({len(content.hashtags)}個)"
        )
    if len(content.x_post) > X_POST_MAX:
        violations.append(f"x_post が{X_POST_MAX}文字を超過しています({len(content.x_post)}文字)")
    if len(content.cta) > CTA_MAX:
        violations.append(f"cta が{CTA_MAX}文字を超過しています({len(content.cta)}文字)")
    return violations


def load_active_prompt(session: Session, agent: str) -> PromptVersion:
    stmt = select(PromptVersion).where(
        PromptVersion.agent == agent, PromptVersion.is_active.is_(True)
    )
    prompt = session.execute(stmt).scalar_one_or_none()
    if prompt is None:
        raise RuntimeError(
            f"有効なプロンプト(agent={agent})が見つかりません。"
            "scripts/seed_prompts.py を実行してください"
        )
    return prompt


def render_prompt(template: str, product: Product, improvement_hint: str | None) -> str:
    product_json = json.dumps(
        {
            "name": product.name,
            "genre_name": product.genre_name,
            "shop_name": product.shop_name,
        },
        ensure_ascii=False,
    )
    prompt = template.replace("{product_json}", product_json)
    if improvement_hint:
        prompt += f"\n\n# 改善指示\n{improvement_hint}\n上記の指示を反映して再生成してください。"
    return prompt


def generate_content(
    session: Session,
    llm_client: LlmClient,
    job_id: uuid.UUID,
    product: Product,
    improvement_hint: str | None = None,
) -> tuple[GeneratedContent, str]:
    prompt_version = load_active_prompt(session, "generator")
    prompt = render_prompt(prompt_version.body, product, improvement_hint)

    settings = get_settings()
    result = llm_client.complete(
        job_id=job_id,
        agent="generator",
        model=settings.model_generator,
        prompt=prompt,
    )
    generated = parse_generated_content(result.text)
    violations = validate_length_constraints(generated)
    if violations:
        raise ValueError("生成コンテンツが制約に違反しています: " + "; ".join(violations))
    return generated, prompt_version.version
