"""Pydantic schemas — Core Base & Module DTOs."""
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel


# ── Agent ──

class AgentOut(BaseModel):
    id: str
    name: str
    email: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Ticket ──

class TicketCreate(BaseModel):
    title: str
    description: str = ""
    customer_name: str
    customer_email: str
    priority: str = "small"  # urgent | medium | small


class TicketOut(BaseModel):
    id: str
    title: str
    description: str
    customer_name: str
    customer_email: str
    priority: str
    status: str
    assigned_agent_id: Optional[str] = None
    assigned_agent_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Claim (Module 1 - INC-0291) ──

class ClaimRequest(BaseModel):
    agent_id: str


# ── Messages (Module 2 - INC-0304) ──

class MessageCreate(BaseModel):
    content: str
    is_private: bool = False
    sender_type: str = "agent"  # agent | customer
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None


class MessageOut(BaseModel):
    id: str
    ticket_id: str
    sender_type: str
    sender_id: Optional[str] = None
    sender_name: str
    content: str
    is_private: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomerMessageOut(BaseModel):
    """Customer-safe DTO: Strictly omits is_private flag and internal metadata."""
    id: str
    ticket_id: str
    sender_type: str
    sender_name: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Audit Logs (Module 3 - INC-0318) ──

class AuditLogOut(BaseModel):
    id: int
    ticket_id: str
    actor_type: str
    actor_id: Optional[str] = None
    actor_name: str
    action: str
    details: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}

