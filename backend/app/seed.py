"""Seed data — 9 agents (Meera + 8 team) and sample tickets."""
from .models import Agent, Ticket
from .database import SessionLocal


SEED_AGENTS = [
    {"id": "a1000001-0000-0000-0000-000000000001", "name": "Meera", "email": "meera@arvo.in", "role": "lead"},
    {"id": "a1000001-0000-0000-0000-000000000002", "name": "Ravi", "email": "ravi@arvo.in", "role": "agent"},
    {"id": "a1000001-0000-0000-0000-000000000003", "name": "Priya", "email": "priya@arvo.in", "role": "agent"},
    {"id": "a1000001-0000-0000-0000-000000000004", "name": "Arjun", "email": "arjun@arvo.in", "role": "agent"},
    {"id": "a1000001-0000-0000-0000-000000000005", "name": "Sneha", "email": "sneha@arvo.in", "role": "agent"},
    {"id": "a1000001-0000-0000-0000-000000000006", "name": "Kiran", "email": "kiran@arvo.in", "role": "agent"},
    {"id": "a1000001-0000-0000-0000-000000000007", "name": "Deepa", "email": "deepa@arvo.in", "role": "agent"},
    {"id": "a1000001-0000-0000-0000-000000000008", "name": "Vikram", "email": "vikram@arvo.in", "role": "agent"},
    {"id": "a1000001-0000-0000-0000-000000000009", "name": "Ananya", "email": "ananya@arvo.in", "role": "agent"},
]

SEED_TICKETS = [
    {
        "id": "INC-0001",
        "title": "Cannot login to production dashboard",
        "description": "Getting 403 error when trying to access the production dashboard since this morning. Entire team is blocked.",
        "customer_name": "Rahul Sharma",
        "customer_email": "rahul@acmecorp.com",
        "priority": "urgent",
        "status": "open",
    },
    {
        "id": "INC-0002",
        "title": "Invoice PDF not generating correctly",
        "description": "Monthly invoice for October shows incorrect tax calculation. Amount is off by approximately 2%.",
        "customer_name": "Nisha Patel",
        "customer_email": "nisha@globaltech.in",
        "priority": "medium",
        "status": "open",
    },
    {
        "id": "INC-0003",
        "title": "How to export data to CSV",
        "description": "We need to export our customer list to CSV format for a quarterly report. Where is the export button?",
        "customer_name": "Amit Kumar",
        "customer_email": "amit@startupxyz.com",
        "priority": "small",
        "status": "open",
    },
    {
        "id": "INC-0004",
        "title": "API rate limiting errors on bulk import",
        "description": "We are hitting rate limit errors (429) when importing more than 500 records via the API.",
        "customer_name": "Fatima Khan",
        "customer_email": "fatima@dataflow.io",
        "priority": "medium",
        "status": "in_progress",
        "assigned_agent_id": "a1000001-0000-0000-0000-000000000002",
    },
    {
        "id": "INC-0005",
        "title": "Password reset email not arriving",
        "description": "Tried resetting password multiple times but the reset email never arrives. Checked spam folder too.",
        "customer_name": "Suresh Reddy",
        "customer_email": "suresh@megamart.com",
        "priority": "urgent",
        "status": "waiting_on_customer",
        "assigned_agent_id": "a1000001-0000-0000-0000-000000000001",
    },
]


def seed_database():
    """Insert seed data if the database is empty."""
    db = SessionLocal()
    try:
        if db.query(Agent).count() > 0:
            return  # Already seeded
        for agent_data in SEED_AGENTS:
            db.add(Agent(**agent_data))
        for ticket_data in SEED_TICKETS:
            db.add(Ticket(**ticket_data))
        db.commit()
    finally:
        db.close()
