"""FastAPI application — Step 0 Core Base."""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update
from sqlalchemy.orm import Session

from .database import engine, get_db, Base
from .models import Agent, Ticket
from .schemas import AgentOut, TicketCreate, TicketOut, ClaimRequest
from .seed import seed_database
from .utils import next_ticket_id


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
    return _ticket_to_out(ticket)

