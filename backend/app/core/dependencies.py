"""Reusable FastAPI dependencies and authorization guards."""
from typing import Optional

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from .config import settings
from .security import decode_token


def get_current_agent(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """FastAPI dependency that resolves the authenticated agent.

    - If a token is provided (via Authorization: Bearer <token> or query param ?token=...):
      validates signature, expiration, and agent status. Raises HTTP 401 if invalid.
    - If NO token is provided:
      - REQUIRE_AUTH=false (default dev/test): returns lead agent for backward compat.
      - REQUIRE_AUTH=true (production): raises HTTP 401.
    """
    from ..models import Agent

    raw_token: Optional[str] = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.removeprefix("Bearer ").strip()
    elif token:
        raw_token = token.strip()

    if raw_token:
        payload = decode_token(raw_token)
        if payload.get("role") == "customer":
            raise HTTPException(status_code=403, detail="Customer accounts cannot access agent helpdesk endpoints.")
        agent_id = payload.get("sub")
        agent = db.query(Agent).filter(Agent.id == agent_id, Agent.is_active == True).first()
        if not agent:
            raise HTTPException(status_code=401, detail="Agent account not found or deactivated.")
        agent._from_jwt = True
        return agent

    if not settings.REQUIRE_AUTH:
        lead = db.query(Agent).filter(Agent.role == "lead").first()
        if not lead:
            lead = db.query(Agent).first()
        return lead

    raise HTTPException(
        status_code=401,
        detail="Authorization header with Bearer token is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_customer(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """FastAPI dependency that resolves the authenticated customer."""
    from ..models import Customer

    raw_token: Optional[str] = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.removeprefix("Bearer ").strip()
    elif token:
        raw_token = token.strip()

    if raw_token:
        payload = decode_token(raw_token)
        customer_id = payload.get("sub")
        customer = db.query(Customer).filter(Customer.id == customer_id, Customer.is_active == True).first()
        if not customer:
            raise HTTPException(status_code=401, detail="Customer account not found or deactivated.")
        customer._from_jwt = True
        return customer

    if not settings.REQUIRE_AUTH:
        cust = db.query(Customer).filter(Customer.email == "customer@acmecorp.com").first()
        if cust:
            return cust

    raise HTTPException(
        status_code=401,
        detail="Customer authorization header with Bearer token is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Resolve authenticated user as either ('agent', Agent) or ('customer', Customer)."""
    from ..models import Agent, Customer

    raw_token: Optional[str] = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.removeprefix("Bearer ").strip()
    elif token:
        raw_token = token.strip()

    if raw_token:
        payload = decode_token(raw_token)
        user_id = payload.get("sub")
        role = payload.get("role")
        if role == "customer":
            cust = db.query(Customer).filter(Customer.id == user_id, Customer.is_active == True).first()
            if not cust:
                raise HTTPException(status_code=401, detail="Customer account not found.")
            return "customer", cust
        else:
            agent = db.query(Agent).filter(Agent.id == user_id, Agent.is_active == True).first()
            if not agent:
                raise HTTPException(status_code=401, detail="Agent account not found.")
            return "agent", agent

    if not settings.REQUIRE_AUTH:
        lead = db.query(Agent).filter(Agent.role == "lead").first()
        return "agent", lead

    raise HTTPException(status_code=401, detail="Bearer token required.")


def get_effective_agent(
    db: Session,
    current_agent,
    explicit_agent_id: Optional[str] = None,
):
    """Resolve acting agent. If authenticated via JWT as a regular agent,
    the token identity cannot be spoofed via explicit_agent_id.
    """
    from ..models import Agent

    if getattr(current_agent, "_from_jwt", False) and current_agent.role not in ("lead", "admin"):
        return current_agent

    if explicit_agent_id:
        target = db.query(Agent).filter(Agent.id == explicit_agent_id).first()
        if target:
            return target
    return current_agent


def verify_ticket_ownership(ticket, agent, action: str = "modify"):
    """Enforce ticket ownership:
    If a ticket is assigned to an agent, another regular agent cannot modify it.
    Only the assigned agent or a lead/admin can modify an assigned ticket.
    """
    if ticket.assigned_agent_id is not None and ticket.assigned_agent_id != agent.id:
        if agent.role not in ("lead", "admin"):
            assigned_name = ticket.assigned_agent.name if ticket.assigned_agent else "another agent"
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden: You cannot {action} a ticket assigned to {assigned_name}.",
            )
