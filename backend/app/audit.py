"""Audit service — Module 3: Immutable Event Sourcing (INC-0318)."""
import logging
from typing import Optional, Any
from sqlalchemy.orm import Session

from .models import AuditLog

logger = logging.getLogger(__name__)


def log_audit(
    db: Session,
    ticket_id: str,
    actor_type: str,
    actor_name: str,
    action: str,
    details: Optional[dict[str, Any]] = None,
    actor_id: Optional[str] = None,
) -> Optional[AuditLog]:
    """Append-only audit event recorder.

    Guarantees non-repudiation and proof for who did what and when.
    Designed with graceful resilience: failure in audit logging never crashes
    the primary business operation.
    """
    try:
        entry = AuditLog(
            ticket_id=ticket_id,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_name=actor_name,
            action=action,
            details=details or {},
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
    except Exception as e:
        logger.error(f"Failed to record audit log for ticket {ticket_id}: {e}")
        return None
