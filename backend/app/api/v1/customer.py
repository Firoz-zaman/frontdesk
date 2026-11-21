"""Customer Portal API router — v1.

Provides dedicated, zero-leakage endpoints strictly scoped to authenticated customers.
Enforces customer data isolation, SLA unfreezing upon customer response,
and real-time event publishing across the customer-agent boundary.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Customer, Ticket, Message
from ...schemas import TicketOut, CustomerMessageOut
from ...audit import log_audit
from ...events import broadcaster
from ...lifecycle import can_reopen_ticket, evaluate_auto_close_tickets
from ...sla import (
    compute_ticket_slas,
    compute_sla_status,
    add_business_minutes,
    calculate_business_minutes_between,
)
from ...utils import next_ticket_id
from ...core.dependencies import get_current_customer
from ...core.security import generate_customer_token

router = APIRouter(prefix="/customer", tags=["Customer Portal"])


class CustomerTicketCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: str = Field("", max_length=5000)
    priority: str = Field("medium", pattern="^(urgent|medium|small)$")


class CustomerMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


def _ticket_to_out(ticket: Ticket) -> TicketOut:
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


@router.get("/tickets", response_model=list[TicketOut])
def list_my_tickets(
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    """List tickets belonging strictly to the authenticated customer."""
    evaluate_auto_close_tickets(db)
    tickets = (
        db.query(Ticket)
        .filter(Ticket.customer_email.ilike(customer.email))
        .order_by(Ticket.created_at.desc())
        .all()
    )
    return [_ticket_to_out(t) for t in tickets]


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
def get_my_ticket(
    ticket_id: str,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    """Retrieve ticket details if owned by the authenticated customer."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    if ticket.customer_email.lower() != customer.email.lower():
        raise HTTPException(status_code=403, detail="Forbidden: You cannot view other customers' tickets.")
    return _ticket_to_out(ticket)


@router.post("/tickets", response_model=TicketOut, status_code=201)
def create_customer_ticket(
    payload: CustomerTicketCreate,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    """Allow customer to submit a new ticket directly from the portal."""
    ticket_id = next_ticket_id(db)
    now = datetime.now(timezone.utc)
    first_resp_due, res_due = compute_ticket_slas(now, payload.priority)

    ticket = Ticket(
        id=ticket_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        customer_name=customer.name,
        customer_email=customer.email,
        priority=payload.priority,
        status="open",
        created_at=now,
        first_response_due_at=first_resp_due,
        resolution_due_at=res_due,
        customer_token_hash=generate_customer_token(ticket_id, customer.email),
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    log_audit(
        db=db,
        ticket_id=ticket.id,
        actor_type="customer",
        actor_id=customer.id,
        actor_name=customer.name,
        action="TICKET_CREATED",
        details={
            "priority": ticket.priority,
            "title": ticket.title,
            "company": customer.company,
        },
    )

    # Broadcast new ticket creation to agent queues
    broadcaster.publish("TICKET_CLAIMED", {
        "ticket_id": ticket.id,
        "customer_name": ticket.customer_name,
        "priority": ticket.priority,
        "status": "open",
    })

    return _ticket_to_out(ticket)


@router.get("/tickets/{ticket_id}/messages", response_model=list[CustomerMessageOut])
def list_customer_messages(
    ticket_id: str,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    """Return public ticket messages. Strictly isolates internal private agent notes."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    if ticket.customer_email.lower() != customer.email.lower():
        raise HTTPException(status_code=403, detail="Forbidden: You cannot view messages for another customer's ticket.")

    # Zero-Leakage Wall: Never query or expose is_private == True
    messages = (
        db.query(Message)
        .filter(Message.ticket_id == ticket_id, Message.is_private == False)
        .order_by(Message.created_at.asc())
        .all()
    )
    return [
        CustomerMessageOut(
            id=m.id,
            ticket_id=m.ticket_id,
            sender_type=m.sender_type,
            sender_name=m.sender_name,
            content=m.content,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.post("/tickets/{ticket_id}/messages", response_model=CustomerMessageOut, status_code=201)
def post_customer_message(
    ticket_id: str,
    payload: CustomerMessageCreate,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    """Customer replies to ticket. Automatically resumes SLA and moves status to in_progress."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    if ticket.customer_email.lower() != customer.email.lower():
        raise HTTPException(status_code=403, detail="Forbidden: You cannot reply to another customer's ticket.")

    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")

    now = datetime.now(timezone.utc)

    # Reopen policy guard if ticket was previously resolved/closed
    if ticket.status in ("done", "closed"):
        allowed, reason = can_reopen_ticket(ticket)
        if not allowed:
            raise HTTPException(status_code=400, detail=reason)
        ticket.status = "in_progress"
        ticket.resolved_at = None
        ticket.closed_at = None

    message = Message(
        ticket_id=ticket_id,
        sender_type="customer",
        sender_id=customer.id,
        sender_name=customer.name,
        content=payload.content.strip(),
        is_private=False,  # Customers can never create private notes
        created_at=now,
    )
    db.add(message)

    # SLA Resumption & Clock Extension: If waiting on customer, resume to in_progress
    if ticket.status == "waiting_on_customer":
        ticket.status = "in_progress"
        if ticket.sla_paused_at is not None:
            paused_minutes = calculate_business_minutes_between(ticket.sla_paused_at, now)
            if paused_minutes > 0:
                if ticket.resolution_due_at is not None:
                    ticket.resolution_due_at = add_business_minutes(ticket.resolution_due_at, paused_minutes)
                if ticket.first_response_due_at is not None and ticket.first_responded_at is None:
                    ticket.first_response_due_at = add_business_minutes(ticket.first_response_due_at, paused_minutes)
                ticket.total_paused_minutes = (ticket.total_paused_minutes or 0) + paused_minutes
            ticket.sla_paused_at = None

    db.commit()
    db.refresh(message)

    # Immutable Audit Log
    log_audit(
        db=db,
        ticket_id=ticket.id,
        actor_type="customer",
        actor_id=customer.id,
        actor_name=customer.name,
        action="CUSTOMER_REPLY_RECEIVED",
        details={
            "ticket_status": ticket.status,
            "preview": payload.content[:100],
        },
    )

    # Real-time event broadcasting to agent dashboards
    broadcaster.publish("CUSTOMER_REPLY_RECEIVED", {
        "ticket_id": ticket_id,
        "sender_type": "customer",
        "sender_name": customer.name,
        "preview": payload.content[:80],
        "status": ticket.status,
    })

    return CustomerMessageOut(
        id=message.id,
        ticket_id=message.ticket_id,
        sender_type=message.sender_type,
        sender_name=message.sender_name,
        content=message.content,
        created_at=message.created_at,
    )
