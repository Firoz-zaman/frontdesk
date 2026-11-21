"""Ticket route endpoints — v1."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import update
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Agent, Ticket
from ...schemas import (
    TicketCreate,
    TicketOut,
    ClaimRequest,
    PriorityUpdateRequest,
    ResolveTicketRequest,
    ReopenTicketRequest,
)
from ...utils import next_ticket_id
from ...audit import log_audit
from ...events import broadcaster
from ...core.security import generate_customer_token
from ...core.dependencies import get_current_agent, get_effective_agent, verify_ticket_ownership
from ...sla import (
    compute_ticket_slas,
    recalculate_sla_on_priority_change,
    compute_sla_status,
)
from ...lifecycle import can_reopen_ticket, evaluate_auto_close_tickets

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def _ticket_to_out(ticket: Ticket) -> TicketOut:
    """Convert a Ticket ORM instance to a TicketOut schema with live SLA health."""
    sla_info = compute_sla_status(ticket)
    return TicketOut(
        id=ticket.id,
        title=ticket.title,
        description=ticket.description,
        customer_name=ticket.customer_name,
        customer_email=ticket.customer_email,
        priority=ticket.priority,
        status=ticket.status,
        assigned_agent_id=ticket.assigned_agent_id,
        assigned_agent_name=ticket.assigned_agent.name if ticket.assigned_agent else None,
        created_at=ticket.created_at,
        first_response_due_at=ticket.first_response_due_at,
        resolution_due_at=ticket.resolution_due_at,
        first_responded_at=ticket.first_responded_at,
        resolved_at=ticket.resolved_at,
        closed_at=ticket.closed_at,
        sla_paused_at=ticket.sla_paused_at,
        sla_status=sla_info,
    )


@router.get("", response_model=list[TicketOut])
def list_tickets(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    evaluate_auto_close_tickets(db)
    query = db.query(Ticket)
    if status:
        query = query.filter(Ticket.status == status)
    tickets = query.order_by(Ticket.created_at.desc()).all()
    return [_ticket_to_out(t) for t in tickets]


@router.post("", response_model=TicketOut, status_code=201)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)):
    p = payload.priority.lower()
    if p not in ("urgent", "medium", "small"):
        raise HTTPException(status_code=400, detail="Invalid priority level. Must be urgent, medium, or small.")

    ticket_id = next_ticket_id(db)
    now = datetime.now(timezone.utc)
    first_resp_due, res_due = compute_ticket_slas(now, p)

    ticket = Ticket(
        id=ticket_id,
        title=payload.title,
        description=payload.description,
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        priority=p,
        created_at=now,
        first_response_due_at=first_resp_due,
        resolution_due_at=res_due,
        customer_token_hash=generate_customer_token(ticket_id, payload.customer_email),
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    log_audit(
        db=db,
        ticket_id=ticket.id,
        actor_type="customer",
        actor_name=ticket.customer_name,
        action="TICKET_CREATED",
        details={
            "title": ticket.title,
            "priority": ticket.priority,
            "customer_email": ticket.customer_email,
        },
    )

    return _ticket_to_out(ticket)


@router.post("/auto-close", response_model=list[TicketOut])
def trigger_auto_close(db: Session = Depends(get_db)):
    """Enforce REQ-SLA-04: Evaluate and auto-close tickets that have been waiting on customer >= 5 working days."""
    closed = evaluate_auto_close_tickets(db)
    return [_ticket_to_out(t) for t in closed]


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: str, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _ticket_to_out(ticket)


@router.post("/{ticket_id}/claim", response_model=TicketOut)
def claim_ticket(
    ticket_id: str,
    payload: ClaimRequest,
    db: Session = Depends(get_db),
    current_agent: Agent = Depends(get_current_agent),
):
    target_agent_id = payload.agent_id
    if getattr(current_agent, "_from_jwt", False) and current_agent.role not in ("lead", "admin"):
        target_agent_id = current_agent.id

    agent = db.query(Agent).filter(Agent.id == target_agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.status in ("done", "closed"):
        raise HTTPException(
            status_code=400,
            detail="Cannot claim a resolved or closed ticket. Reopen the ticket first."
        )

    if ticket.assigned_agent_id is not None:
        assigned_name = ticket.assigned_agent.name if ticket.assigned_agent else "another agent"
        raise HTTPException(
            status_code=409,
            detail=f"Ticket has already been claimed by {assigned_name}."
        )

    # Atomic conditional update (INC-0291)
    result = db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.assigned_agent_id.is_(None))
        .values(assigned_agent_id=payload.agent_id, status="in_progress")
    )

    if result.rowcount == 0:
        db.rollback()
        current = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        assigned_name = current.assigned_agent.name if current and current.assigned_agent else "another agent"
        raise HTTPException(
            status_code=409,
            detail=f"Ticket was just claimed by {assigned_name} in a concurrent session."
        )

    db.commit()
    db.refresh(ticket)

    log_audit(
        db=db,
        ticket_id=ticket_id,
        actor_type="agent",
        actor_id=agent.id,
        actor_name=agent.name,
        action="TICKET_CLAIMED",
        details={
            "assigned_to": agent.name,
            "status": "in_progress",
        },
    )

    broadcaster.publish("TICKET_CLAIMED", {
        "ticket_id": ticket_id,
        "agent_id": agent.id,
        "agent_name": agent.name,
    })

    return _ticket_to_out(ticket)


@router.patch("/{ticket_id}/priority", response_model=TicketOut)
def update_ticket_priority(
    ticket_id: str,
    payload: PriorityUpdateRequest,
    agent_id: Optional[str] = Query(None),
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.status in ("done", "closed"):
        raise HTTPException(status_code=400, detail="Cannot change priority of a resolved or closed ticket.")

    # Ownership guard: only assigned agent or lead/admin can change priority
    acting_agent = get_effective_agent(db, current_agent, payload.agent_id or agent_id)
    verify_ticket_ownership(ticket, acting_agent, action="change priority on")

    new_p = payload.priority.lower()
    if new_p not in ("urgent", "medium", "small"):
        raise HTTPException(status_code=400, detail="Invalid priority level. Must be urgent, medium, or small.")

    prev_p = ticket.priority
    if prev_p == new_p:
        return _ticket_to_out(ticket)

    now = datetime.now(timezone.utc)
    new_resp, new_res = recalculate_sla_on_priority_change(
        current_time=now,
        new_priority=new_p,
        first_responded_at=ticket.first_responded_at,
    )

    ticket.priority = new_p
    if new_resp is not None:
        ticket.first_response_due_at = new_resp
    ticket.resolution_due_at = new_res

    effective_agent_id = acting_agent.id
    actor_name = acting_agent.name

    log_audit(
        db=db,
        ticket_id=ticket.id,
        actor_type="agent",
        actor_id=effective_agent_id,
        actor_name=actor_name,
        action="PRIORITY_CHANGED",
        details={
            "previous_priority": prev_p,
            "new_priority": new_p,
            "first_response_due_at": ticket.first_response_due_at.isoformat() if ticket.first_response_due_at else None,
            "resolution_due_at": ticket.resolution_due_at.isoformat() if ticket.resolution_due_at else None,
        },
    )

    db.commit()
    db.refresh(ticket)

    broadcaster.publish("TICKET_PRIORITY_CHANGED", {
        "ticket_id": ticket.id,
        "priority": new_p,
    })

    return _ticket_to_out(ticket)


@router.post("/{ticket_id}/resolve", response_model=TicketOut)
def resolve_ticket(
    ticket_id: str,
    payload: Optional[ResolveTicketRequest] = None,
    agent_id: Optional[str] = Query(None),
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.status in ("done", "closed"):
        raise HTTPException(status_code=400, detail="Ticket is already resolved or closed.")

    # Ownership guard: only assigned agent or lead/admin can resolve
    acting_agent = get_effective_agent(db, current_agent, (payload.agent_id if payload else None) or agent_id)
    verify_ticket_ownership(ticket, acting_agent, action="resolve")

    now = datetime.now(timezone.utc)
    ticket.status = "done"
    ticket.resolved_at = now
    ticket.sla_paused_at = None

    effective_agent_id = acting_agent.id
    actor_name = acting_agent.name

    log_audit(
        db=db,
        ticket_id=ticket.id,
        actor_type="agent",
        actor_id=effective_agent_id,
        actor_name=actor_name,
        action="TICKET_RESOLVED",
        details={
            "status": "done",
            "resolved_at": now.isoformat(),
        },
    )

    db.commit()
    db.refresh(ticket)

    broadcaster.publish("TICKET_RESOLVED", {
        "ticket_id": ticket_id,
        "resolved_by": actor_name,
        "resolved_at": now.isoformat(),
    })

    return _ticket_to_out(ticket)


@router.post("/{ticket_id}/reopen", response_model=TicketOut)
def reopen_ticket(
    ticket_id: str,
    payload: Optional[ReopenTicketRequest] = None,
    agent_id: Optional[str] = Query(None),
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    allowed, reason = can_reopen_ticket(ticket)
    if not allowed:
        raise HTTPException(status_code=400, detail=reason)

    # Ownership guard: only assigned agent or lead/admin can reopen
    acting_agent = get_effective_agent(db, current_agent, (payload.agent_id if payload else None) or agent_id)
    verify_ticket_ownership(ticket, acting_agent, action="reopen")

    now = datetime.now(timezone.utc)
    prev_status = ticket.status
    ticket.status = "in_progress"
    ticket.resolved_at = None
    ticket.closed_at = None
    ticket.sla_paused_at = None

    effective_agent_id = acting_agent.id
    actor_name = acting_agent.name

    log_audit(
        db=db,
        ticket_id=ticket.id,
        actor_type="agent",
        actor_id=effective_agent_id,
        actor_name=actor_name,
        action="TICKET_REOPENED",
        details={
            "previous_status": prev_status,
            "new_status": "in_progress",
            "reason": payload.reason if payload else None,
        },
    )

    db.commit()
    db.refresh(ticket)

    broadcaster.publish("TICKET_REOPENED", {
        "ticket_id": ticket.id,
        "agent_id": effective_agent_id,
        "agent_name": actor_name,
        "status": "in_progress",
    })

    return _ticket_to_out(ticket)
