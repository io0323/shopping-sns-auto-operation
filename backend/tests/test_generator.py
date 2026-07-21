from typing import Any

from app.agents.generator import (
    GeneratedContent,
    parse_generated_content,
    render_prompt,
    strip_code_fence,
    validate_length_constraints,
)
from app.models import Product


def _valid_content(**overrides: Any) -> GeneratedContent:
    data: dict[str, Any] = {
        "title": "かわいい新作コスメ",
        "description": "あ" * 100,
        "hashtags": ["#a", "#b", "#c", "#d", "#e"],
        "x_post": "投稿テキスト #ad",
        "cta": "今すぐチェック",
    }
    data.update(overrides)
    return GeneratedContent.model_validate(data)


def test_strip_code_fence_removes_json_fence() -> None:
    text = '```json\n{"a": 1}\n```'
    assert strip_code_fence(text) == '{"a": 1}'


def test_strip_code_fence_no_fence_returns_as_is() -> None:
    assert strip_code_fence('{"a": 1}') == '{"a": 1}'


def test_parse_generated_content_from_fenced_json() -> None:
    text = (
        '```json\n{"title": "t", "description": "d", "hashtags": ["#a"], '
        '"x_post": "x", "cta": "c"}\n```'
    )
    content = parse_generated_content(text)
    assert content.title == "t"
    assert content.hashtags == ["#a"]


def test_validate_length_constraints_all_ok() -> None:
    assert validate_length_constraints(_valid_content()) == []


def test_validate_length_constraints_title_too_long() -> None:
    violations = validate_length_constraints(_valid_content(title="あ" * 31))
    assert any("title" in v for v in violations)


def test_validate_length_constraints_description_out_of_range() -> None:
    violations = validate_length_constraints(_valid_content(description="短い"))
    assert any("description" in v for v in violations)


def test_validate_length_constraints_hashtags_too_few() -> None:
    violations = validate_length_constraints(_valid_content(hashtags=["#a"]))
    assert any("hashtags" in v for v in violations)


def test_validate_length_constraints_x_post_too_long() -> None:
    violations = validate_length_constraints(_valid_content(x_post="あ" * 121))
    assert any("x_post" in v for v in violations)


def test_validate_length_constraints_cta_too_long() -> None:
    violations = validate_length_constraints(_valid_content(cta="あ" * 21))
    assert any("cta" in v for v in violations)


def test_render_prompt_embeds_product_and_hint() -> None:
    template = "商品: {product_json}"
    product = Product(
        item_code="shop1:0001",
        name="テスト商品",
        genre_id="100283",
        genre_name="スイーツ",
        shop_code="shop1",
        shop_name="ショップ",
        item_url="https://item.rakuten.co.jp/x/",
    )

    prompt = render_prompt(template, product, improvement_hint=None)
    assert "テスト商品" in prompt
    assert "改善指示" not in prompt

    prompt_with_hint = render_prompt(template, product, improvement_hint="もっと短く")
    assert "改善指示" in prompt_with_hint
    assert "もっと短く" in prompt_with_hint
