"""SQLAlchemy hooks for auditable schema approval/rejection actions."""
from __future__ import annotations
import json
import uuid
from datetime import datetime
from sqlalchemy import event, inspect, text
from app.db.models import DataSource

_REGISTERED = False

def register_schema_audit_hooks() -> None:
    global _REGISTERED
    if _REGISTERED:
        return

    @event.listens_for(DataSource, "before_update")
    def _before_update(mapper, connection, target):
        history = inspect(target).attrs.mapping.history
        if not history.has_changes():
            return
        old = history.deleted[0] if history.deleted else {}
        new = history.added[0] if history.added else target.mapping or {}
        old_status = ((old or {}).get("_schema_approval") or {}).get("status")
        new_status = ((new or {}).get("_schema_approval") or {}).get("status")
        if new_status not in {"approved", "rejected"} or new_status == old_status:
            return
        old_approval = (old or {}).get("_schema_approval") or {}
        new_approval = (new or {}).get("_schema_approval") or {}
        candidate_hash = new_approval.get("candidate_hash") or old_approval.get("candidate_hash")
        semantic = {k: v for k, v in (new or {}).items() if not str(k).startswith("_")}
        connection.execute(
            text("INSERT INTO schema_approval_audit (id,store_id,datasource_id,action,candidate_hash,mapping,created_at) VALUES (:id,:store_id,:datasource_id,:action,:candidate_hash,:mapping,:created_at)"),
            {
                "id": str(uuid.uuid4()),
                "store_id": target.store_id,
                "datasource_id": target.id,
                "action": new_status,
                "candidate_hash": candidate_hash,
                "mapping": json.dumps(semantic, separators=(",", ":")),
                "created_at": datetime.utcnow(),
            },
        )

    _REGISTERED = True
