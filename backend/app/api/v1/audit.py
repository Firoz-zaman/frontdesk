"""Audit trail route endpoints — v1."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Ticket, AuditLog
from ...schemas import AuditLogOut

router = APIRouter(prefix="/tickets", tags=["Audit"])


@router.get("/{ticket_id}/audit", response_model=list[AuditLogOut])
def get_ticket_audit_trail(ticket_id: str, db: Session = Depends(get_db)):
    """Fetch append-only chronological audit log for non-repudiation (INC-0318).
    Strictly read-only; no update or delete endpoints exist.
    """
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    logs = (
        db.query(AuditLog)
        .filter(AuditLog.ticket_id == ticket_id)
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        .all()
    )
    return [AuditLogOut.model_validate(log) for log in logs]
