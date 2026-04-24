"""Audit logging helpers for admin and system actions."""

from typing import Any

from database.models import AuditLog
from database.session import get_db_session


def write_audit_log(
    action: str,
    entity_type: str,
    entity_id: str,
    result: str = "SUCCESS",
    actor_user_id: int | None = None,
    reason: str | None = None,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    with get_db_session() as session:
        session.add(
            AuditLog(
                actor_user_id=actor_user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                result=result,
                reason=reason,
                old_values=old_values,
                new_values=new_values,
                metadata_json=metadata,
            )
        )
