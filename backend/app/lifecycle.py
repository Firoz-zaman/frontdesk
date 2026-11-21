"""Pluggable Module 5: Ticket Lifecycle Policies (Inactivity & Reopening).

Rules strictly following Arvo Systems specification:
- REQ-SLA-04: Auto-Close Inactive Tickets: If ticket remains in 'waiting_on_customer'
  for >= 5 working days (45 working hours = 2,700 business minutes), system auto-closes it.
  Generates system audit log: "Auto-closed due to 1 week of customer inactivity."
- REQ-SLA-05: Reopen Window Guard: Reopening a resolved or closed ticket is allowed
  within 7 calendar days of resolution/closure.
  Attempts after 7 calendar days are strictly rejected with HTTP 400:
  "Tickets closed more than 1 week ago cannot be reopened. Please submit a new ticket."
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from sqlalchemy.orm import Session

from .sla import calculate_business_minutes_between, _normalize_dt
from .models import Ticket
from .audit import log_audit

REOPEN_WINDOW_DAYS = 7
AUTO_CLOSE_BUSINESS_MINUTES = 5 * 9 * 60  # 5 working days * 9 hours/day * 60 min/hr = 2,700 business minutes


def can_reopen_ticket(ticket: Any, current_time: Optional[datetime] = None) -> tuple[bool, Optional[str]]:
    """Evaluate whether a ticket is eligible to be reopened.

    Returns:
        (is_allowed: bool, rejection_reason: Optional[str])
    """
    status = getattr(ticket, "status", None)
    if status not in ("done", "closed"):
        return False, f"Only resolved or closed tickets can be reopened. Current status is '{status}'."

    ref_time = getattr(ticket, "resolved_at", None) or getattr(ticket, "closed_at", None)
    if ref_time is None:
        # If no explicit resolved/closed timestamp exists, allow reopening
        return True, None

    now = current_time or datetime.now(timezone.utc)
    ref_time = _normalize_dt(ref_time)
    now = _normalize_dt(now)

    elapsed = now - ref_time
    if elapsed > timedelta(days=REOPEN_WINDOW_DAYS):
        return (
            False,
            "Tickets closed more than 1 week ago cannot be reopened. Please submit a new ticket.",
        )

    return True, None


def should_auto_close(ticket: Any, current_time: Optional[datetime] = None) -> bool:
    """Check if a ticket in 'waiting_on_customer' has exceeded 5 working days of inactivity."""
    if getattr(ticket, "status", None) != "waiting_on_customer":
        return False

    paused_at = getattr(ticket, "sla_paused_at", None)
    if paused_at is None:
        return False

    now = current_time or datetime.now(timezone.utc)
    elapsed_business_min = calculate_business_minutes_between(paused_at, now)
    return elapsed_business_min >= AUTO_CLOSE_BUSINESS_MINUTES


def evaluate_auto_close_tickets(db: Session, current_time: Optional[datetime] = None) -> list[Ticket]:
    """Inspect all tickets waiting on customers and auto-close those exceeding 5 working days."""
    now = current_time or datetime.now(timezone.utc)
    candidates = (
        db.query(Ticket)
        .filter(Ticket.status == "waiting_on_customer", Ticket.sla_paused_at.isnot(None))
        .all()
    )

    auto_closed: list[Ticket] = []
    for t in candidates:
        if should_auto_close(t, now):
            t.status = "closed"
            t.closed_at = now
            t.sla_paused_at = None

            log_audit(
                db=db,
                ticket_id=t.id,
                actor_type="system",
                actor_id=None,
                actor_name="System Automator",
                action="AUTO_CLOSED",
                details={
                    "reason": "Auto-closed due to 1 week of customer inactivity (5 working days / 45 hours).",
                    "closed_at": now.isoformat(),
                },
            )
            auto_closed.append(t)

    if auto_closed:
        db.commit()
        from .events import broadcaster
        for t in auto_closed:
            db.refresh(t)
            broadcaster.publish("TICKET_RESOLVED", {
                "ticket_id": t.id,
                "status": "closed",
                "resolved_by": "System Automator",
                "closed_at": now.isoformat(),
            })

    return auto_closed
