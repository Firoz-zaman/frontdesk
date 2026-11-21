"""FastAPI application — Step 0 Core Base."""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update
from sqlalchemy.orm import Session

from .database import engine, get_db, Base
from .models import Agent, Ticket, Message, AuditLog
from .schemas import (
    AgentOut,
    TicketCreate,
    TicketOut,
    ClaimRequest,
    MessageCreate,
    MessageOut,
    CustomerMessageOut,
    AuditLogOut,
)
from .seed import seed_database
from .utils import next_ticket_id
from .audit import log_audit


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables and seed on startup
    Base.metadata.create_all(bind=engine)
    seed_database()
    yield


app = FastAPI(title="Frontdesk", version="0.1.0", lifespan=lifespan)

# CORS — allow the Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ──

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


# ── Agents ──

@app.get("/api/agents", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db)):
    return db.query(Agent).order_by(Agent.name).all()


# ── Tickets ──

def _ticket_to_out(ticket: Ticket) -> TicketOut:
    """Convert a Ticket ORM instance to a TicketOut schema."""
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
    )


@app.get("/api/tickets", response_model=list[TicketOut])
def list_tickets(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Ticket)
    if status:
        query = query.filter(Ticket.status == status)
    tickets = query.order_by(Ticket.created_at.desc()).all()
    return [_ticket_to_out(t) for t in tickets]


@app.get("/api/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: str, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _ticket_to_out(ticket)


@app.post("/api/tickets", response_model=TicketOut, status_code=201)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)):
    ticket_id = next_ticket_id(db)
    ticket = Ticket(
        id=ticket_id,
        title=payload.title,
        description=payload.description,
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        priority=payload.priority,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    # INC-0318: Record immutable ticket creation audit event
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


# ── Module 1: Atomic Claiming (INC-0291) ──

@app.post("/api/tickets/{ticket_id}/claim", response_model=TicketOut)
def claim_ticket(ticket_id: str, payload: ClaimRequest, db: Session = Depends(get_db)):
    # 1. Verify agent exists
    agent = db.query(Agent).filter(Agent.id == payload.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # 2. Check ticket existence
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # 3. Check if already claimed prior to execution
    if ticket.assigned_agent_id is not None:
        assigned_name = ticket.assigned_agent.name if ticket.assigned_agent else "another agent"
        raise HTTPException(
            status_code=409,
            detail=f"Ticket has already been claimed by {assigned_name}."
        )

    # 4. Atomic conditional update to eliminate race condition (INC-0291)
    result = db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.assigned_agent_id.is_(None))
        .values(assigned_agent_id=payload.agent_id, status="in_progress")
    )

    if result.rowcount == 0:
        db.rollback()
        # Concurrently claimed by another agent
        current = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        assigned_name = current.assigned_agent.name if current and current.assigned_agent else "another agent"
        raise HTTPException(
            status_code=409,
            detail=f"Ticket was just claimed by {assigned_name} in a concurrent session."
        )

    db.commit()
    db.refresh(ticket)

    # INC-0318: Record immutable ticket claiming audit event
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

    return _ticket_to_out(ticket)


# ── Module 2: Dual-Mode Messaging & Note Isolation (INC-0304) ──

@app.get("/api/tickets/{ticket_id}/messages")
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
        # Strictly exclude any message marked as private at the DB query level
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


@app.post("/api/tickets/{ticket_id}/messages", response_model=MessageOut, status_code=201)
def post_ticket_message(
    ticket_id: str,
    payload: MessageCreate,
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    sender_name = payload.sender_name
    sender_type = payload.sender_type
    is_private = payload.is_private

    if sender_type == "customer":
        # Customers can NEVER post private internal notes
        is_private = False
        sender_name = sender_name or ticket.customer_name
    elif sender_type == "agent":
        if payload.sender_id and not sender_name:
            agent = db.query(Agent).filter(Agent.id == payload.sender_id).first()
            if agent:
                sender_name = agent.name
        sender_name = sender_name or "Support Agent"

    message = Message(
        ticket_id=ticket_id,
        sender_type=sender_type,
        sender_id=payload.sender_id,
        sender_name=sender_name,
        content=payload.content,
        is_private=is_private,
    )
    db.add(message)

    # State transition: If agent replies publicly to customer, status moves to 'waiting_on_customer'
    if sender_type == "agent" and not is_private and ticket.status in ("open", "in_progress"):
        ticket.status = "waiting_on_customer"

    # State transition: If customer replies back, ticket status moves back to 'in_progress'
    elif sender_type == "customer" and ticket.status == "waiting_on_customer":
        ticket.status = "in_progress"

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

    return MessageOut.model_validate(message)


# ── Module 3: Immutable Audit Event Sourcing (INC-0318) ──

@app.get("/api/tickets/{ticket_id}/audit", response_model=list[AuditLogOut])
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



