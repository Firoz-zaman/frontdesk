"""Pydantic schemas — Core Base & Module DTOs."""
from datetime import datetime
from typing import Optional

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
