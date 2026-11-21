"""Ticket ID generator — produces sequential INC-XXXX identifiers."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Ticket


def next_ticket_id(db: Session) -> str:
    """Return the next available unique ticket ID like INC-0006."""
    tickets = db.query(Ticket.id).all()
    max_num = 0
    for (tid,) in tickets:
        if tid and tid.startswith("INC-"):
            try:
                num = int(tid[4:])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"INC-{(max_num + 1):04d}"
