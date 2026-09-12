import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Product
from app.sync.media_models import ProductMediaHealth


@pytest.mark.asyncio
async def test_media_health_paginates_without_filter_after_limit(monkeypatch):
    from app.sync import media_health

    engine = create_engine("sqlite:///:memory:")
    Product.__table__.create(engine)
    ProductMediaHealth.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    db.add_all([
        Product(
            id="p1", store_id="store-1", source_datasource_id="ds-1",
            name="Product 1", is_active=True, product_url="https://example.test/p1",
            image_url="https://example.test/p1.jpg", source_fingerprint="fp1",
        ),
        Product(
            id="p2", store_id="store-1", source_datasource_id="ds-1",
            name="Product 2", is_active=True, product_url="https://example.test/p2",
            image_url="https://example.test/p2.jpg", source_fingerprint="fp2",
        ),
    ])
    db.commit()

    async def fake_verify_product_urls(urls, concurrency=20):
        return {url: True for url in urls}

    async def fake_verify_image_urls(urls):
        return {url: True for url in urls}

    monkeypatch.setattr(media_health, "verify_product_urls", fake_verify_product_urls)
    monkeypatch.setattr(media_health, "verify_image_urls", fake_verify_image_urls)

    result = await media_health.verify_and_persist_media_health(
        db, store_id="store-1", datasource_id="ds-1", batch_size=1
    )

    assert result["products_checked"] == 2
    assert result["products_verified"] == 2
    assert result["products_reused"] == 0
    assert result["url"] == {"missing": 0, "valid": 2, "broken": 0}
    assert result["image"] == {"missing": 0, "valid": 2, "broken": 0}
    assert db.query(ProductMediaHealth).count() == 2
    db.close()
