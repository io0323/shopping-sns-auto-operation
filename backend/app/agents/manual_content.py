"""チャットUIで手動生成したコンテンツを取り込む(設計書§13 手動生成取込)。

`ANTHROPIC_API_KEY` を有効化する前に、`prompts/generator/gen-v1.txt` の妥当性を
実商品で確認するための経路。Generator Agent(`app.agents.generator`)と
Evaluator(`app.agents.evaluator`)のロジックを再利用するだけで、それらの
既存フロー(daily_pipeline)には一切手を入れない。
"""

import json

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agents.evaluator import load_ng_words, rule_check
from app.agents.generator import GeneratedContent, strip_code_fence
from app.models import Candidate, Content, Product

GENERATION_SOURCE_MANUAL = "manual"


class ManualContentParseError(Exception):
    """貼り付けられたJSONが解釈できない。[field_errors]はフィールド単位の理由。"""

    def __init__(self, field_errors: list[str]) -> None:
        super().__init__("; ".join(field_errors))
        self.field_errors = field_errors


def parse_manual_content(text: str) -> GeneratedContent:
    """チャットが返した文字列を[GeneratedContent]へ変換する。

    コードフェンス(```json ... ```)付きで貼られても剥がす(Generator Agentが
    LLM応答に対して行うのと同じ[strip_code_fence]を使う)。
    """
    raw = strip_code_fence(text)
    if not raw.strip():
        raise ManualContentParseError(["本文: 空です"])

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManualContentParseError(
            [f"本文: JSONとして解釈できません({exc.msg}, {exc.lineno}行目)"]
        ) from exc

    if not isinstance(data, dict):
        raise ManualContentParseError(["本文: JSONオブジェクト({...})である必要があります"])

    try:
        return GeneratedContent.model_validate(data)
    except ValidationError as exc:
        field_errors = [
            f"{'.'.join(str(part) for part in error['loc']) or '本文'}: {error['msg']}"
            for error in exc.errors()
        ]
        raise ManualContentParseError(field_errors) from exc


def import_manual_content(
    session: Session,
    candidate: Candidate,
    product: Product,
    generated: GeneratedContent,
    prompt_version: str,
) -> tuple[Content, list[str]]:
    """手動生成結果を`contents`へ保存し、ルールベースチェックの結果を返す。

    LLM評価(`run_evaluator`)は行わないため`status`は`evaluated`にせず、必ず
    `needs_review`とする(人がレビュー画面で確認してから承認する)。
    """
    violations = rule_check(generated, load_ng_words())

    content = Content(
        product_id=product.id,
        candidate_id=candidate.id,
        title=generated.title,
        description=generated.description,
        hashtags=generated.hashtags,
        x_post=generated.x_post,
        cta=generated.cta,
        prompt_version=prompt_version,
        generation_source=GENERATION_SOURCE_MANUAL,
        regen_count=0,
        status="needs_review",
        eval_comment="; ".join(violations) if violations else None,
    )
    session.add(content)

    candidate.status = "generated"
    session.add(candidate)
    session.commit()
    return content, violations
