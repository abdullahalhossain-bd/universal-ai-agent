"""Safe stale-product lifecycle: missing -> warning -> archive after grace syncs."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

def apply_stale_policy(db: Session, *, store_id: str, datasource_id: str, seen_ids: set[str], grace_syncs: int = 2) -> dict:
    now = datetime.utcnow(); grace = max(1, int(grace_syncs)); params = {"store_id": store_id, "datasource_id": datasource_id, "now": now}
    if seen_ids:
        stmt = text("SELECT product_id FROM products WHERE store_id=:store_id AND source_datasource_id=:datasource_id AND product_id NOT IN :seen_ids AND is_active = TRUE").bindparams(bindparam("seen_ids", expanding=True))
        rows = db.execute(stmt, {**params, "seen_ids": list(seen_ids)}).scalars().all()
    else:
        rows = db.execute(text("SELECT product_id FROM products WHERE store_id=:store_id AND source_datasource_id=:datasource_id AND is_active = TRUE"), params).scalars().all()
    newly_missing = 0; newly_archived = 0
    if rows:
        before = text("SELECT COUNT(*) FROM products WHERE store_id=:store_id AND source_datasource_id=:datasource_id AND product_id IN :ids AND stale_misses=0 AND is_active = TRUE").bindparams(bindparam("ids", expanding=True))
        newly_missing = int(db.execute(before, {**params, "ids": rows}).scalar() or 0)
        update = text("UPDATE products SET stale_misses=stale_misses+1, stale_since=COALESCE(stale_since,:now) WHERE store_id=:store_id AND source_datasource_id=:datasource_id AND product_id IN :ids").bindparams(bindparam("ids", expanding=True))
        db.execute(update, {**params, "ids": rows})
        archive = text("UPDATE products SET is_active=FALSE WHERE store_id=:store_id AND source_datasource_id=:datasource_id AND product_id IN :ids AND stale_misses > :grace AND is_active = TRUE").bindparams(bindparam("ids", expanding=True))
        newly_archived = int(db.execute(archive, {**params, "ids": rows, "grace": grace}).rowcount or 0)
    if seen_ids:
        seen = text("UPDATE products SET last_seen_at=:now, stale_since=NULL, stale_misses=0, is_active=TRUE WHERE store_id=:store_id AND source_datasource_id=:datasource_id AND product_id IN :ids").bindparams(bindparam("ids", expanding=True))
        db.execute(seen, {**params, "ids": list(seen_ids)})
    stale_count = int(db.execute(text("SELECT COUNT(*) FROM products WHERE store_id=:store_id AND source_datasource_id=:datasource_id AND stale_since IS NOT NULL AND is_active = TRUE"), params).scalar() or 0)
    archived_count = int(db.execute(text("SELECT COUNT(*) FROM products WHERE store_id=:store_id AND source_datasource_id=:datasource_id AND is_active = FALSE"), params).scalar() or 0)
    return {"stale_active": stale_count, "archived": archived_count, "newly_archived": newly_archived, "newly_missing": newly_missing, "currently_missing": len(rows), "grace_syncs": grace}
