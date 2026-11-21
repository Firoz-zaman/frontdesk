"""Ticket ID generator — produces sequential INC-XXXX identifiers."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Ticket


def next_ticket_id(db: Session) -> str:
    """Return the next available ticket ID like INC-0006."""
    result = db.query(func.count(Ticket.id)).scalar()
    return f"INC-{(result + 1):04d}"
