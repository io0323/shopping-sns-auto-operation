import importlib.util
from pathlib import Path
from types import ModuleType

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Candidate, Content, Job, LlmUsage, Product, ProductMetric, Result
from tests.conftest import make_product

SEED_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed_demo_data.py"


def _load_seed_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_demo_data", SEED_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _count(session: Session, model: type) -> int:
    return int(session.execute(select(func.count()).select_from(model)).scalar_one())


def test_seed_populates_data_for_every_screen(
    db_session_factory: sessionmaker[Session],
) -> None:
    seed_demo_data = _load_seed_module()
    session = db_session_factory()

    seed_demo_data.seed(session)

    item_count = len(seed_demo_data.DEMO_ITEMS)
    # 候補一覧・レビュー・投稿キュー画面の元データ
    assert _count(session, Product) == item_count
    assert _count(session, Candidate) == item_count
    assert _count(session, Content) == item_count
    # 直近7日分のスナップショット(スコア算出の入力)
    assert _count(session, ProductMetric) == item_count * seed_demo_data.METRIC_DAYS
    # 分析画面・ダッシュボードのKPI
    assert _count(session, Result) > 0
    # ダッシュボードの月間LLMコスト
    assert _count(session, LlmUsage) > 0

    statuses = set(session.execute(select(Content.status)).scalars().all())
    # レビュー画面(evaluated/needs_review)と投稿キュー(approved)の両方に出る状態を作る
    assert {"evaluated", "needs_review", "approved"} <= statuses

    candidates = session.execute(select(Candidate)).scalars().all()
    for candidate in candidates:
        assert set(candidate.score_breakdown) == {
            "rank_trend",
            "review_growth",
            "rating",
            "seasonality",
            "price_fit",
            "competition",
        }
        assert candidate.score > 0

    # 学習レポート画面のAPIは pipeline/step/status で絞るため、step名は実パイプラインと
    # 同じ"learning"でなければ画面に出ない(demo-learning等にすると拾われない)。
    learning_job = session.execute(
        select(Job).where(Job.pipeline == "weekly", Job.step == "learning")
    ).scalar_one()
    result = (learning_job.payload or {})["result"]
    assert result["status"] == "completed"
    assert result["report"]["summary"]
    assert result["proposed_prompt_version_id"]


def test_seeded_learning_report_is_returned_by_api(
    api_client: TestClient, db_session_factory: sessionmaker[Session]
) -> None:
    seed_demo_data = _load_seed_module()
    seed_demo_data.seed(db_session_factory())

    body = api_client.get("/api/v1/analytics/learning-report").json()

    assert body["status"] == "completed"
    assert body["report"]["summary"]
    assert body["proposed_prompt_version"] is not None


def test_main_aborts_when_data_exists_without_force(
    db_session_factory: sessionmaker[Session],
) -> None:
    seed_demo_data = _load_seed_module()
    session = db_session_factory()
    make_product(session, item_code="shop1:0001")

    assert seed_demo_data.main([]) == 1

    assert _count(session, Product) == 1
    assert _count(session, Candidate) == 0


def test_force_reseeds_without_duplicating_and_keeps_real_rows(
    db_session_factory: sessionmaker[Session],
) -> None:
    seed_demo_data = _load_seed_module()
    session = db_session_factory()
    real_product = make_product(session, item_code="shop1:0001", name="実データ商品")

    assert seed_demo_data.main(["--force"]) == 0
    assert seed_demo_data.main(["--force"]) == 0

    item_count = len(seed_demo_data.DEMO_ITEMS)
    session.expire_all()
    demo_products = (
        session.execute(
            select(Product).where(
                Product.item_code.like(f"{seed_demo_data.DEMO_ITEM_CODE_PREFIX}%")
            )
        )
        .scalars()
        .all()
    )
    assert len(demo_products) == item_count
    # 実データ(demo:以外)は--forceでも削除しない
    assert session.get(Product, real_product.id) is not None
