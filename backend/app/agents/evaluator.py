import json
import re
import uuid
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.generator import (
    GeneratedContent,
    generate_content,
    load_active_prompt,
    strip_code_fence,
    validate_length_constraints,
)
from app.clients.llm import LlmClient
from app.core.config import get_settings
from app.models import Candidate, Content, Product

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
NG_WORDS_PATH = CONFIG_DIR / "ng_words.yaml"

MAX_REGENERATIONS = 3
PASS_THRESHOLD = 80


class EvalScores(BaseModel):
    natural: int
    readability: int
    appeal: int
    uniqueness: int
    compliance: int


class EvalResult(BaseModel):
    total: int
    scores: EvalScores
    verdict: str
    improvement: str | None = None


class NgWordsConfig(BaseModel):
    patterns: list[str] = Field(default_factory=list)


def load_ng_words(path: Path | None = None) -> NgWordsConfig:
    target = path or NG_WORDS_PATH
    with target.open(encoding="utf-8") as f:
        raw: dict[str, list[str]] = yaml.safe_load(f)
    patterns: list[str] = []
    for category_patterns in raw.values():
        patterns.extend(category_patterns)
    return NgWordsConfig(patterns=patterns)


def rule_check(content: GeneratedContent, ng_words: NgWordsConfig) -> list[str]:
    violations = validate_length_constraints(content)

    if "#ad" not in content.x_post:
        violations.append("x_post に #ad が含まれていません")

    haystack = "\n".join(
        [content.title, content.description, content.x_post, content.cta, *content.hashtags]
    )
    for pattern in ng_words.patterns:
        if re.search(pattern, haystack):
            violations.append(f"禁止表現に抵触しています: {pattern}")

    return violations


def render_eval_prompt(template: str, content: GeneratedContent, recent_posts: list[str]) -> str:
    content_json = json.dumps(content.model_dump(), ensure_ascii=False)
    recent_posts_text = "\n".join(recent_posts) if recent_posts else "(過去投稿なし)"
    prompt = template.replace("{content_json}", content_json)
    prompt = prompt.replace("{recent_posts}", recent_posts_text)
    return prompt


def parse_eval_result(text: str) -> EvalResult:
    raw = strip_code_fence(text)
    data = json.loads(raw)
    return EvalResult.model_validate(data)


def run_evaluator(
    session: Session,
    llm_client: LlmClient,
    job_id: uuid.UUID,
    content: GeneratedContent,
    recent_posts: list[str],
) -> EvalResult:
    prompt_version = load_active_prompt(session, "evaluator")
    prompt = render_eval_prompt(prompt_version.body, content, recent_posts)

    settings = get_settings()
    result = llm_client.complete(
        job_id=job_id,
        agent="evaluator",
        model=settings.model_evaluator,
        prompt=prompt,
    )
    return parse_eval_result(result.text)


def run_generate_and_evaluate(
    session: Session,
    llm_client: LlmClient,
    job_id: uuid.UUID,
    product: Product,
    candidate: Candidate,
    recent_posts: list[str] | None = None,
) -> Content:
    recent_posts = recent_posts or []
    ng_words = load_ng_words()

    improvement_hint: str | None = None
    generated: GeneratedContent | None = None
    prompt_version_str = ""
    last_eval: EvalResult | None = None
    regen_count = 0

    for attempt in range(MAX_REGENERATIONS):
        regen_count = attempt
        generated, prompt_version_str = generate_content(
            session, llm_client, job_id, product, improvement_hint
        )

        rule_violations = rule_check(generated, ng_words)
        if rule_violations:
            improvement_hint = "; ".join(rule_violations)
            last_eval = None
            continue

        last_eval = run_evaluator(session, llm_client, job_id, generated, recent_posts)
        if last_eval.total >= PASS_THRESHOLD:
            break
    assert generated is not None
    passed = last_eval is not None and last_eval.total >= PASS_THRESHOLD

    content = Content(
        product_id=product.id,
        candidate_id=candidate.id,
        title=generated.title,
        description=generated.description,
        hashtags=generated.hashtags,
        x_post=generated.x_post,
        cta=generated.cta,
        prompt_version=prompt_version_str,
        regen_count=regen_count,
        status="evaluated" if passed else "needs_review",
    )
    if last_eval is not None:
        content.quality_score = float(last_eval.total)
        content.quality_breakdown = last_eval.scores.model_dump()
        content.eval_comment = last_eval.improvement
    elif improvement_hint is not None:
        content.eval_comment = improvement_hint

    session.add(content)
    session.commit()
    return content
    session.commit()
    return content
    session.commit()
    return content
