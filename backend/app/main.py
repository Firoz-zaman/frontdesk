"""FastAPI application — Step 0 Core Base."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import update, text
from sqlalchemy.orm import Session

from .database import engine, get_db, Base
from .models import Agent, Ticket, Message, AuditLog
from .schemas import (
    AgentOut,
    LoginRequest,
    TokenOut,
    TicketCreate,
    TicketOut,
    ClaimRequest,
    MessageCreate,
    MessageOut,
    CustomerMessageOut,
    AuditLogOut,
    PriorityUpdateRequest,
    ResolveTicketRequest,
    ReopenTicketRequest,
)
from .seed import seed_database
from .utils import next_ticket_id
from .audit import log_audit
from .auth import (
    verify_password,
    create_access_token,
    generate_customer_token,
    get_current_agent,
)
from .events import broadcaster, event_generator
from .sla import (
    compute_ticket_slas,
    recalculate_sla_on_priority_change,
    compute_sla_status,
    add_business_minutes,
    calculate_business_minutes_between,
)
from .lifecycle import (
    can_reopen_ticket,
    should_auto_close,
    evaluate_auto_close_tickets,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables and seed on startup
    Base.metadata.create_all(bind=engine)
    # ── Schema migrations (idempotent ALTER TABLE) ──────────────────────────────
    with engine.connect() as conn:
        # Stage 5: closed_at on tickets
        ticket_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(tickets)"))]
        if "closed_at" not in ticket_cols:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN closed_at DATETIME"))
            conn.commit()
        # v2: customer_token_hash on tickets
        if "customer_token_hash" not in ticket_cols:
            conn.execute(text("ALTER TABLE tickets ADD COLUMN customer_token_hash VARCHAR(64)"))
            conn.commit()
        # v2: auth fields on agents
        agent_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(agents)"))]
        if "password_hash" not in agent_cols:
            conn.execute(text("ALTER TABLE agents ADD COLUMN password_hash VARCHAR(255) NOT NULL DEFAULT ''"))
            conn.commit()
        if "is_active" not in agent_cols:
            conn.execute(text("ALTER TABLE agents ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))
            conn.commit()
        if "last_login_at" not in agent_cols:
            conn.execute(text("ALTER TABLE agents ADD COLUMN last_login_at DATETIME"))
            conn.commit()
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


# ── Auth (v2) ──

@app.post("/api/auth/login", response_model=TokenOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate an agent with email + password. Returns a signed JWT."""
    agent = db.query(Agent).filter(
        Agent.email == payload.email,
        Agent.is_active == True,
    ).first()
    if not agent or not verify_password(payload.password, agent.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    agent.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(agent)
    token = create_access_token(agent.id, agent.email, agent.role)
    return TokenOut(access_token=token, agent=AgentOut.model_validate(agent))


@app.get("/api/auth/me", response_model=AgentOut)
def get_me(current_agent: Agent = Depends(get_current_agent)):
    """Return the currently authenticated agent's profile."""
    return AgentOut.model_validate(current_agent)


# ── SSE Real-Time Events (v2) ──

@app.get("/api/events/stream")
async def event_stream(
    request: Request,
    current_agent: Agent = Depends(get_current_agent),
):
    """Server-Sent Events endpoint. Streams real-time typed events to connected agents."""
    queue = await broadcaster.subscribe()
    return StreamingResponse(
        event_generator(request, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


# ── Agents ──

@app.get("/api/agents", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db)):
    return db.query(Agent).order_by(Agent.name).all()


# ── Tickets ──

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


@app.get("/api/tickets", response_model=list[TicketOut])
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


@app.get("/api/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: str, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _ticket_to_out(ticket)


@app.post("/api/tickets", response_model=TicketOut, status_code=201)
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
        # v2: Generate customer magic link token for self-service access
        customer_token_hash=generate_customer_token(ticket_id, payload.customer_email),
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

    # 3. Check terminal state
    if ticket.status in ("done", "closed"):
        raise HTTPException(
            status_code=400,
            detail="Cannot claim a resolved or closed ticket. Reopen the ticket first."
        )

    # 4. Check if already claimed prior to execution
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

    # v2: Broadcast real-time event to all connected SSE clients
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(broadcaster.broadcast("TICKET_CLAIMED", {
                "ticket_id": ticket_id,
                "agent_id": agent.id,
                "agent_name": agent.name,
            }))
    except Exception:
        pass  # Broadcast failure must never break the primary request

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
            # Reopen ticket to in_progress upon valid customer reply
            ticket.status = "in_progress"
            ticket.resolved_at = None
            ticket.closed_at = None
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
            pass  # Broadcast failure must never break the primary request

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


# ── Module 4: Working Hours SLA Management & Resolution ──

@app.patch("/api/tickets/{ticket_id}/priority", response_model=TicketOut)
def update_ticket_priority(
    ticket_id: str,
    payload: PriorityUpdateRequest,
    agent_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Answers the unanswered meeting question:
    'What happens to the timer if we change a ticket to urgent in the middle?'

    Recalculates the SLA clock dynamically from escalation point.
    """
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.status in ("done", "closed"):
        raise HTTPException(status_code=400, detail="Cannot change priority of a resolved or closed ticket.")

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

    # Audit the escalation
    effective_agent_id = payload.agent_id or agent_id
    actor_name = "Support Agent"
    if effective_agent_id:
        agent = db.query(Agent).filter(Agent.id == effective_agent_id).first()
        if agent:
            actor_name = agent.name

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
    return _ticket_to_out(ticket)


@app.post("/api/tickets/{ticket_id}/resolve", response_model=TicketOut)
def resolve_ticket(
    ticket_id: str,
    payload: Optional[ResolveTicketRequest] = None,
    agent_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Mark a ticket as resolved ('done')."""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.status in ("done", "closed"):
        raise HTTPException(status_code=400, detail="Ticket is already resolved or closed.")

    now = datetime.now(timezone.utc)
    ticket.status = "done"
    ticket.resolved_at = now
    ticket.sla_paused_at = None

    effective_agent_id = (payload.agent_id if payload else None) or agent_id
    actor_name = "Support Agent"
    if effective_agent_id:
        agent = db.query(Agent).filter(Agent.id == effective_agent_id).first()
        if agent:
            actor_name = agent.name

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

    # v2: Broadcast TICKET_RESOLVED event to all connected SSE clients
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(broadcaster.broadcast("TICKET_RESOLVED", {
                "ticket_id": ticket_id,
                "resolved_by": actor_name,
                "resolved_at": now.isoformat(),
            }))
    except Exception:
        pass  # Broadcast failure must never break the primary request

    return _ticket_to_out(ticket)


# ── Module 5: Lifecycle Inactivity & Reopening Policies ──

@app.post("/api/tickets/{ticket_id}/reopen", response_model=TicketOut)
def reopen_ticket(
    ticket_id: str,
    payload: Optional[ReopenTicketRequest] = None,
    agent_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Enforce REQ-SLA-05: Reopen allowed within 7 calendar days of resolution/closure.
    Attempts after 7 calendar days are strictly rejected with HTTP 400.
    """
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    allowed, reason = can_reopen_ticket(ticket)
    if not allowed:
        raise HTTPException(status_code=400, detail=reason)

    now = datetime.now(timezone.utc)
    prev_status = ticket.status
    ticket.status = "in_progress"
    ticket.resolved_at = None
    ticket.closed_at = None
    ticket.sla_paused_at = None

    effective_agent_id = (payload.agent_id if payload else None) or agent_id
    actor_name = "Support Agent"
    if effective_agent_id:
        agent = db.query(Agent).filter(Agent.id == effective_agent_id).first()
        if agent:
            actor_name = agent.name

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
    return _ticket_to_out(ticket)


@app.post("/api/tickets/auto-close", response_model=list[TicketOut])
def trigger_auto_close(db: Session = Depends(get_db)):
    """Enforce REQ-SLA-04: Evaluate and auto-close tickets that have been waiting on customer >= 5 working days."""
    closed = evaluate_auto_close_tickets(db)
    return [_ticket_to_out(t) for t in closed]





