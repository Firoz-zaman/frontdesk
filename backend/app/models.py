"""SQLAlchemy models — Step 0 Core Base: agents & tickets only."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Boolean, JSON
from sqlalchemy.orm import relationship

from .database import Base


def _utcnow():
    return datetime.now(timezone.utc)


def _new_uuid():
    return str(uuid.uuid4())


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    role = Column(String(20), nullable=False, default="agent")  # agent | lead | admin
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationship (back-ref from tickets)
    assigned_tickets = relationship("Ticket", back_populates="assigned_agent")


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(String(20), primary_key=True)  # e.g. INC-0001
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    customer_name = Column(String(100), nullable=False)
    customer_email = Column(String(150), nullable=False)
    priority = Column(String(10), nullable=False, default="small")  # urgent | medium | small
    status = Column(String(25), nullable=False, default="open")  # open | in_progress | waiting_on_customer | done | closed
    assigned_agent_id = Column(String(36), ForeignKey("agents.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationship
    assigned_agent = relationship("Agent", back_populates="assigned_tickets")
    messages = relationship("Message", back_populates="ticket", order_by="Message.created_at", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="ticket", order_by="AuditLog.created_at.asc()", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    ticket_id = Column(String(20), ForeignKey("tickets.id"), nullable=False)
    sender_type = Column(String(20), nullable=False, default="agent")  # agent | customer | system
    sender_id = Column(String(100), nullable=True)  # Agent UUID or customer email
    sender_name = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    is_private = Column(Boolean, nullable=False, default=False)  # INC-0304: True = Internal Team Note
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    ticket = relationship("Ticket", back_populates="messages")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(String(20), ForeignKey("tickets.id"), nullable=False)
    actor_type = Column(String(20), nullable=False)  # agent | customer | system
    actor_id = Column(String(100), nullable=True)
    actor_name = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)  # TICKET_CREATED, TICKET_CLAIMED, PUBLIC_REPLIED, INTERNAL_NOTE_ADDED, etc.
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    ticket = relationship("Ticket", back_populates="audit_logs")


