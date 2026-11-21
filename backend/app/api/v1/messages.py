"""Message route endpoints — v1 (Dual-mode communication & private note isolation)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Agent, Ticket, Message
from ...schemas import MessageCreate, MessageOut, CustomerMessageOut
from ...audit import log_audit
from ...events import broadcaster
from ...lifecycle import can_reopen_ticket
from ...core.dependencies import get_current_agent, get_effective_agent, verify_ticket_ownership
from ...sla import add_business_minutes, calculate_business_minutes_between

router = APIRouter(prefix="/tickets", tags=["Messages"])


@router.get("/{ticket_id}/messages")
def list_ticket_messages(
    ticket_id: str,
    scope: str = Query("agent", description="'agent' includes private notes; 'customer' strictly isolates them"),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    query = db.query(Message).filter(Message.ticket_id == ticket_id)

    # INC-0304: Zero-leakage wall for customer view
    if scope == "customer":
        messages = query.filter(Message.is_private == False).order_by(Message.created_at.asc()).all()
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

    # Agent view: includes all messages and indicates is_private
    messages = query.order_by(Message.created_at.asc()).all()
    return [
        MessageOut(
            id=m.id,
            ticket_id=m.ticket_id,
            sender_type=m.sender_type,
            sender_id=m.sender_id,
            sender_name=m.sender_name,
            content=m.content,
            is_private=m.is_private,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.post("/{ticket_id}/messages", response_model=MessageOut, status_code=201)
def post_ticket_message(
    ticket_id: str,
    payload: MessageCreate,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if not payload.content or not payload.content.strip():
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")

    sender_name = payload.sender_name
    sender_type = payload.sender_type
    is_private = payload.is_private

    if sender_type == "customer":
        # Customers can NEVER post private internal notes
        is_private = False
        sender_name = sender_name or ticket.customer_name

        # If customer sends message on resolved/closed ticket, verify reopen policy
        if ticket.status in ("done", "closed"):
            allowed, reason = can_reopen_ticket(ticket)
            if not allowed:
                raise HTTPException(status_code=400, detail=reason)
            ticket.status = "in_progress"
            ticket.resolved_at = None
            ticket.closed_at = None
    elif sender_type == "agent":
        acting_agent = get_effective_agent(db, current_agent, payload.sender_id)
        if not is_private:
            verify_ticket_ownership(ticket, acting_agent, action="send public replies on")
        sender_name = sender_name or acting_agent.name

    message = Message(
        ticket_id=ticket_id,
        sender_type=sender_type,
        sender_id=payload.sender_id,
        sender_name=sender_name,
        content=payload.content,
        is_private=is_private,
    )
    db.add(message)

    now = datetime.now(timezone.utc)

    # State transition & SLA Pause: If agent replies publicly to customer, status moves to 'waiting_on_customer'
    if sender_type == "agent" and not is_private:
        if ticket.status in ("open", "in_progress"):
            ticket.status = "waiting_on_customer"
        if ticket.first_responded_at is None:
            ticket.first_responded_at = now
        # REQ-SLA-03: Freeze SLA timer while waiting on customer
        ticket.sla_paused_at = now

    # State transition & SLA Resume: If customer replies back, ticket status moves back to 'in_progress'
    elif sender_type == "customer":
        if ticket.status == "waiting_on_customer":
            ticket.status = "in_progress"
        # REQ-SLA-03: Unfreeze SLA timer and extend deadlines by business duration waited
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

    # INC-0318: Record non-repudiation audit event for every communication
    action = "INTERNAL_NOTE_ADDED" if is_private else ("PUBLIC_REPLY_SENT" if sender_type == "agent" else "CUSTOMER_REPLY_RECEIVED")
    log_audit(
        db=db,
        ticket_id=ticket_id,
        actor_type=sender_type,
        actor_id=payload.sender_id,
        actor_name=sender_name,
        action=action,
        details={
            "is_private": is_private,
            "status": ticket.status,
            "preview": payload.content[:120] + ("..." if len(payload.content) > 120 else ""),
        },
    )

    # v2: Broadcast real-time event (only public messages — never expose private notes)
    if not is_private:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(broadcaster.broadcast(action, {
                    "ticket_id": ticket_id,
                    "sender_type": sender_type,
                    "sender_name": sender_name,
                    "preview": payload.content[:80],
                }))
        except Exception:
            pass

    return MessageOut.model_validate(message)
