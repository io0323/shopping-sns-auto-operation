"""動作確認用のデモデータを投入するseedスクリプト。

実行: cd backend && uv run python scripts/seed_demo_data.py

DBが空だとフロントの全画面がゼロ表示になり動作確認にならないため、7画面
(ダッシュボード/候補一覧/レビュー/投稿キュー/実績取込/分析/学習レポート)が
すべて何かしら表示される状態を作る。

投入するProductは`item_code`が`demo:`始まりで、本スクリプトが作った行を識別できる。
既存データがある状態では誤投入を防ぐため中断し、`--force`指定時のみ`demo:`始まりの
行だけを削除して入れ直す(パイプラインが作った実データは削除しない)。

スコアはハードコードせず、実際のSelection Agent(app.agents.selection)の計算式に
7日分のproduct_metricsを通して算出するため、候補一覧に出るスコアと内訳は
本番同様に整合する。
"""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.agents.research import load_strategy
from app.agents.selection import (
    compute_score,
    compute_score_breakdown,
    load_scoring_weights,
    load_seasonality,
)
from app.core.db import get_session_factory
from app.models import (
    Candidate,
    Content,
    Job,
    LlmUsage,
    Product,
    ProductMetric,
    PromptVersion,
    Result,
)

DEMO_ITEM_CODE_PREFIX = "demo:"
# jobsは`step`をAPI側のフィルタ条件(pipeline/step/status)に合わせる必要があるため、
# 名前では区別できない。payloadにこのマーカーを入れて--force時の削除対象を判別する。
SEED_MARKER_KEY = "seeded_by"
SEED_MARKER_VALUE = "seed_demo_data"
METRIC_DAYS = 7


@dataclass(frozen=True)
class DemoItem:
    """1商品ぶんのデモデータ定義。"""

    suffix: str
    name: str
    genre_id: str
    genre_name: str
    shop_code: str
    shop_name: str
    price: int
    point_rate: int
    review_count_start: int
    review_count_end: int
    review_average: float
    rank_start: int
    rank_end: int
    title: str
    description: str
    hashtags: list[str]
    x_post: str
    cta: str
    status: str
    quality_breakdown: dict[str, int]
    eval_comment: str
    clicks: int
    conversions: int
    revenue: int
    scheduled_offset_days: int | None = None
    llm_usage: list[tuple[str, str, int, int, float]] = field(default_factory=list)


# 本文はconfig/ng_words.yaml(価格・在庫・断定表現の禁止)に抵触しない文面にしてある。
DEMO_ITEMS: tuple[DemoItem, ...] = (
    DemoItem(
        suffix="0001",
        name="軽量ステンレスボトル 500ml 真空断熱 保冷保温",
        genre_id="551177",
        genre_name="生活雑貨",
        shop_code="demo-living",
        shop_name="リビングマート(デモ)",
        price=2480,
        point_rate=10,
        review_count_start=1620,
        review_count_end=1842,
        review_average=4.52,
        rank_start=14,
        rank_end=3,
        title="朝の氷が夕方まで残る、軽量ステンレスボトル",
        description=(
            "500mlで約280gと軽く、通勤バッグに入れても肩に負担がかかりません。"
            "真空断熱の二重構造で冷たさが長続きし、結露しにくいので書類と一緒に持ち歩けます。"
            "口径が広く氷を入れやすいところも日常使いで効いてきます。"
        ),
        hashtags=["水筒", "ステンレスボトル", "通勤グッズ", "時短家事", "楽天room"],
        x_post="500mlで約280g。この軽さで真空断熱なのはうれしい。 #ad",
        cta="詳細は商品ページでチェックしてみてください",
        status="evaluated",
        quality_breakdown={
            "natural": 18,
            "readability": 18,
            "appeal": 17,
            "uniqueness": 17,
            "compliance": 18,
        },
        eval_comment="訴求と正確性のバランスが取れています。数値の裏付けも明確です。",
        clicks=46,
        conversions=2,
        revenue=496,
        llm_usage=[
            ("generator", "claude-sonnet-5", 4820, 1360, 41.2),
            ("evaluator", "claude-haiku-4-5", 2180, 420, 6.8),
        ],
    ),
    DemoItem(
        suffix="0002",
        name="珪藻土バスマット 大判 60×39cm 速乾 抗菌 やすり付き",
        genre_id="551177",
        genre_name="生活雑貨",
        shop_code="demo-sanitary",
        shop_name="サニタリーラボ(デモ)",
        price=1980,
        point_rate=12,
        review_count_start=2980,
        review_count_end=3204,
        review_average=4.61,
        rank_start=9,
        rank_end=2,
        title="足裏さらさら、大判サイズの珪藻土バスマット",
        description=(
            "上がった瞬間に水気が引いていく感覚が心地よい大判タイプです。"
            "60×39cmあるので二人ぶんの足元をカバーでき、洗濯の手間がかかりません。"
            "吸水力が落ちてきたら付属のやすりで表面を削ればもとの状態に戻せます。"
        ),
        hashtags=["珪藻土バスマット", "バスグッズ", "お風呂上がり", "洗濯しない", "楽天room"],
        x_post="バスマットの洗濯から解放されたい人におすすめ。 #ad",
        cta="サイズ違いもあるので商品ページで確認してみてください",
        status="approved",
        quality_breakdown={
            "natural": 19,
            "readability": 18,
            "appeal": 18,
            "uniqueness": 18,
            "compliance": 18,
        },
        eval_comment="体験が具体的で読みやすく、規約面の懸念もありません。",
        clicks=80,
        conversions=4,
        revenue=792,
        scheduled_offset_days=1,
        llm_usage=[("generator", "claude-sonnet-5", 4610, 1290, 39.5)],
    ),
    DemoItem(
        suffix="0003",
        name="焼き菓子アソート 12種 個包装 ギフトボックス入り",
        genre_id="100283",
        genre_name="スイーツ・お菓子",
        shop_code="demo-sweets",
        shop_name="パティスリーデモ",
        price=3200,
        point_rate=8,
        review_count_start=740,
        review_count_end=889,
        review_average=4.44,
        rank_start=21,
        rank_end=8,
        title="個包装で配りやすい、焼き菓子12種のアソート",
        description=(
            "フィナンシェやクッキーなど12種類が個包装で入っていて、配る相手を選びません。"
            "ギフトボックス入りなので、そのまま手土産にできるのが便利なところです。"
            "日持ちするタイプなので、贈るタイミングを選ばずに済みます。"
        ),
        hashtags=["焼き菓子", "ギフト", "手土産", "個包装", "楽天room"],
        x_post="個包装12種のアソート。手土産に迷ったときの安全牌。 #ad",
        cta="内容の詳細は商品ページで確認できます",
        status="evaluated",
        quality_breakdown={
            "natural": 17,
            "readability": 18,
            "appeal": 16,
            "uniqueness": 15,
            "compliance": 18,
        },
        eval_comment="読みやすい一方で、独自性の面ではもう一段の掘り下げが可能です。",
        clicks=24,
        conversions=1,
        revenue=598,
        llm_usage=[("evaluator", "claude-haiku-4-5", 2050, 390, 6.3)],
    ),
    DemoItem(
        suffix="0004",
        name="ミドルゲージ ニットカーディガン ゆったりシルエット",
        genre_id="100371",
        genre_name="レディースファッション",
        shop_code="demo-apparel",
        shop_name="デモアパレル",
        price=5480,
        point_rate=6,
        review_count_start=310,
        review_count_end=352,
        review_average=4.18,
        rank_start=33,
        rank_end=19,
        title="羽織るだけで様になる、ミドルゲージのニットカーディガン",
        description=(
            "肩を落としたゆったりシルエットで、インナーを選ばずに羽織れます。"
            "ミドルゲージなので朝晩の冷え込みにも対応しやすい厚みです。"
            "洗濯機で洗えるタイプなので、日常の手入れがしやすいところも扱いやすいです。"
        ),
        hashtags=["カーディガン", "ニット", "秋コーデ", "きれいめカジュアル", "楽天room"],
        x_post="肩落ちシルエットのカーデ、羽織るだけで様になる。 #ad",
        cta="カラー展開は商品ページをご覧ください",
        status="needs_review",
        quality_breakdown={
            "natural": 15,
            "readability": 16,
            "appeal": 14,
            "uniqueness": 13,
            "compliance": 14,
        },
        eval_comment="訴求が一般的で、素材や着用感の具体性が不足しています。再生成を推奨します。",
        clicks=0,
        conversions=0,
        revenue=0,
    ),
)

LEARNING_REPORT = {
    "summary": (
        "生活雑貨ジャンルの成果が全体の約7割を占めた。"
        "使用シーンを具体的な時間帯や動作で描写した投稿がクリック率で優位。"
    ),
    "high_performer_patterns": [
        "冒頭1文で使用シーンを時間帯まで具体化している",
        "サイズ・重量など検証可能な数値を1〜2個に絞って提示している",
        "ハッシュタグを5個以内に抑えている",
    ],
    "low_performer_patterns": [
        "商品名の言い換えに終始し、体験の描写が無い",
        "訴求点を3つ以上詰め込んで焦点がぼやけている",
    ],
    "recommendations": [
        "冒頭1文を「いつ・どこで・どう変わるか」の型で固定する",
        "数値の提示は2個までに制限する",
        "ファッション系は素材と着用感の記述を必須項目にする",
    ],
}

PROPOSED_PROMPT_BODY = """あなたは楽天ROOMの投稿文を作成するアシスタントです。

# 出力の型
- 冒頭1文は「いつ・どこで・どう変わるか」を必ず含める
- 検証可能な数値の提示は2個まで
- ハッシュタグは5個以内
- 価格・ポイント倍率・在庫状況には言及しない

# 入力
商品名・ジャンル・レビュー評価・想定利用シーン
"""


def _demo_item_code(suffix: str) -> str:
    return f"{DEMO_ITEM_CODE_PREFIX}{suffix}"


def count_existing(session: Session) -> dict[str, int]:
    """seedが触る主要テーブルの件数を返す。"""
    counts: dict[str, int] = {}
    for label, model in (
        ("products", Product),
        ("candidates", Candidate),
        ("contents", Content),
        ("results", Result),
    ):
        counts[label] = session.execute(select(func.count()).select_from(model)).scalar_one()
    return counts


def delete_demo_rows(session: Session) -> None:
    """本スクリプトが投入した行(demo:始まりのProductとその関連)だけを削除する。"""
    product_ids = list(
        session.execute(
            select(Product.id).where(Product.item_code.like(f"{DEMO_ITEM_CODE_PREFIX}%"))
        )
        .scalars()
        .all()
    )
    if product_ids:
        content_ids = list(
            session.execute(select(Content.id).where(Content.product_id.in_(product_ids)))
            .scalars()
            .all()
        )
        session.execute(delete(Result).where(Result.product_id.in_(product_ids)))
        if content_ids:
            session.execute(delete(Content).where(Content.id.in_(content_ids)))
        session.execute(delete(Candidate).where(Candidate.product_id.in_(product_ids)))
        session.execute(delete(ProductMetric).where(ProductMetric.product_id.in_(product_ids)))
        session.execute(delete(Product).where(Product.id.in_(product_ids)))

    demo_job_ids = [
        job.id
        for job in session.execute(select(Job)).scalars().all()
        if (job.payload or {}).get(SEED_MARKER_KEY) == SEED_MARKER_VALUE
    ]
    if demo_job_ids:
        session.execute(delete(LlmUsage).where(LlmUsage.job_id.in_(demo_job_ids)))
        session.execute(delete(Job).where(Job.id.in_(demo_job_ids)))

    session.execute(delete(PromptVersion).where(PromptVersion.version.like("demo-%")))


def _seed_metrics(session: Session, product: Product, item: DemoItem, today: date) -> None:
    """直近METRIC_DAYS日ぶんのproduct_metricsを、順位が上がりレビューが増える形で作る。"""
    span = METRIC_DAYS - 1
    for offset in range(METRIC_DAYS):
        progress = offset / span
        snapshot_date = today - timedelta(days=span - offset)
        review_count = round(
            item.review_count_start + (item.review_count_end - item.review_count_start) * progress
        )
        rank = round(item.rank_start + (item.rank_end - item.rank_start) * progress)
        session.add(
            ProductMetric(
                product_id=product.id,
                snapshot_date=snapshot_date,
                price=item.price,
                point_rate=item.point_rate,
                review_count=review_count,
                review_average=item.review_average,
                rank=rank,
                rank_genre_id=item.genre_id,
            )
        )


def _metrics_for(session: Session, product: Product) -> Sequence[ProductMetric]:
    return (
        session.execute(
            select(ProductMetric)
            .where(ProductMetric.product_id == product.id)
            .order_by(ProductMetric.snapshot_date.asc())
        )
        .scalars()
        .all()
    )


def seed(session: Session, today: date | None = None) -> None:
    today = today or date.today()
    now = datetime.now(UTC)

    weights = load_scoring_weights()
    seasonality = load_seasonality()
    strategy = load_strategy()

    demo_job = Job(
        pipeline="daily",
        step="generate",
        status="done",
        payload={
            SEED_MARKER_KEY: SEED_MARKER_VALUE,
            "run_date": today.isoformat(),
        },
        started_at=now - timedelta(minutes=6),
        finished_at=now - timedelta(minutes=1),
    )
    session.add(demo_job)
    session.flush()

    for item in DEMO_ITEMS:
        product = Product(
            item_code=_demo_item_code(item.suffix),
            name=item.name,
            genre_id=item.genre_id,
            genre_name=item.genre_name,
            shop_code=item.shop_code,
            shop_name=item.shop_name,
            item_url=f"https://item.rakuten.co.jp/{item.shop_code}/{item.suffix}/",
            image_url=None,
            excluded=False,
        )
        session.add(product)
        session.flush()

        _seed_metrics(session, product, item, today)
        session.flush()

        metrics = _metrics_for(session, product)
        breakdown = compute_score_breakdown(
            metrics[0], metrics[-1], item.genre_id, strategy.price_band, seasonality, today
        )
        candidate = Candidate(
            product_id=product.id,
            selected_date=today,
            score=compute_score(breakdown, weights),
            score_breakdown=breakdown,
            status="selected",
        )
        session.add(candidate)
        session.flush()

        scheduled_at = (
            now + timedelta(days=item.scheduled_offset_days)
            if item.scheduled_offset_days is not None
            else None
        )
        content = Content(
            product_id=product.id,
            candidate_id=candidate.id,
            title=item.title,
            description=item.description,
            hashtags=item.hashtags,
            x_post=item.x_post,
            cta=item.cta,
            quality_score=float(sum(item.quality_breakdown.values())),
            quality_breakdown=item.quality_breakdown,
            eval_comment=item.eval_comment,
            regen_count=0,
            prompt_version="gen-v1",
            status=item.status,
            scheduled_at=scheduled_at,
            edited_by_human=False,
        )
        session.add(content)
        session.flush()

        if item.clicks or item.conversions or item.revenue:
            session.add(
                Result(
                    product_id=product.id,
                    content_id=content.id,
                    report_date_from=today - timedelta(days=METRIC_DAYS),
                    report_date_to=today,
                    clicks=item.clicks,
                    conversions=item.conversions,
                    revenue=item.revenue,
                    source="csv_import",
                )
            )

        for agent, model, input_tokens, output_tokens, cost in item.llm_usage:
            session.add(
                LlmUsage(
                    job_id=demo_job.id,
                    agent=agent,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost_jpy=cost,
                )
            )

    proposed = PromptVersion(
        agent="generator",
        version="demo-gen-v2",
        body=PROPOSED_PROMPT_BODY,
        is_active=False,
        note="seed_demo_data.py が投入した改善提案(デモ)",
    )
    session.add(proposed)
    session.flush()

    # 学習レポート画面は pipeline=weekly / step=learning / status=done の最新ジョブを引くため、
    # step名は実パイプラインと揃える(揃えないと画面に出ない)。
    session.add(
        Job(
            pipeline="weekly",
            step="learning",
            status="done",
            payload={
                SEED_MARKER_KEY: SEED_MARKER_VALUE,
                "run_date": (today - timedelta(days=1)).isoformat(),
                "result": {
                    "status": "completed",
                    "data_point_count": 42,
                    "report": LEARNING_REPORT,
                    "proposed_prompt_version_id": str(proposed.id),
                },
            },
            started_at=now - timedelta(minutes=9),
            finished_at=now - timedelta(minutes=5),
        )
    )

    session.commit()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="動作確認用のデモデータを投入する")
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存データがあっても実行する(demo:始まりの既存デモ行は削除して入れ直す)",
    )
    args = parser.parse_args(argv)

    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            counts = count_existing(session)
        except OperationalError:
            print(
                "テーブルが見つかりません。先に `uv run alembic upgrade head` を実行してください。",
                file=sys.stderr,
            )
            return 1

        existing = {label: count for label, count in counts.items() if count > 0}
        if existing and not args.force:
            detail = ", ".join(f"{label}={count}件" for label, count in existing.items())
            print(
                f"既存データが見つかりました({detail})。重複投入を避けるため中断します。\n"
                "投入する場合は --force を付けて再実行してください"
                "(demo:始まりの既存デモ行のみ削除して入れ直します)。",
                file=sys.stderr,
            )
            return 1

        if args.force:
            delete_demo_rows(session)
            session.commit()

        seed(session)

    print(
        f"デモデータを投入しました(商品{len(DEMO_ITEMS)}件"
        f"/候補{len(DEMO_ITEMS)}件"
        f"/コンテンツ{len(DEMO_ITEMS)}件)。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
