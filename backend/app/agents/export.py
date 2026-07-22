from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Content, Product
from app.schemas.export import ExportItem

POST_CHECKLIST = (
    "商品URL・画像が正しく表示されているか確認する",
    "本文に価格・ポイント倍率の記載がないか確認する",
    "X投稿文に #ad 表記が含まれているか確認する",
)


def build_room_text(content: Content) -> str:
    return "\n\n".join([content.title, content.description, " ".join(content.hashtags)])


def build_export_item(content: Content, product: Product) -> ExportItem:
    return ExportItem(
        content_id=content.id,
        product_id=product.id,
        product_name=product.name,
        item_url=product.item_url,
        room_text=build_room_text(content),
        x_text=content.x_post,
        has_ad_disclosure="#ad" in content.x_post,
        checklist=list(POST_CHECKLIST),
        scheduled_at=content.scheduled_at,
    )


def build_export_queue(session: Session) -> list[ExportItem]:
    stmt = (
        select(Content, Product)
        .join(Product, Content.product_id == Product.id)
        .where(Content.status == "approved")
        .order_by(
            Content.scheduled_at.is_(None), Content.scheduled_at.asc(), Content.created_at.asc()
        )
    )
    rows = session.execute(stmt).all()
    return [build_export_item(content, product) for content, product in rows]
