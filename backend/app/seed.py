"""Seed data — 9 agents (Meera + 8 team) and sample tickets.

v2: All agents seeded with Argon2id hash of default password "arvo2026!".
    Password hash is updated on each startup if the field is empty (migration-safe).
"""
from datetime import datetime, timezone
from .models import Agent, Ticket, Customer
from .database import SessionLocal
from .sla import compute_ticket_slas
from .auth import hash_password, generate_customer_token

# Default password for all seeded accounts (documented; change in production)
_DEFAULT_PASSWORD = "arvo2026!"


SEED_CUSTOMERS = [
    {
        "id": "c1000001-0000-0000-0000-000000000001",
        "name": "Rahul Sharma",
        "email": "customer@acmecorp.com",
        "company": "Acme Corporation",
    },
    {
        "id": "c1000001-0000-0000-0000-000000000002",
        "name": "Nisha Patel",
        "email": "nisha@globaltech.in",
        "company": "GlobalTech Solutions",
    },
]


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
    """Insert seed data if the database is empty.

    v2 migration: If agents already exist but have an empty password_hash,
    backfill with the default Argon2id hash. This is idempotent and safe to
    run on every startup against an existing database.
    """
    db = SessionLocal()
    try:
        if db.query(Agent).count() == 0:
            # Fresh database: insert all agents and tickets
            now = datetime.now(timezone.utc)
            pwd_hash = hash_password(_DEFAULT_PASSWORD)
            for agent_data in SEED_AGENTS:
                db.add(Agent(**agent_data, password_hash=pwd_hash))
            for ticket_data in SEED_TICKETS:
                t = Ticket(**ticket_data)
                t.created_at = now
                resp_due, res_due = compute_ticket_slas(now, t.priority)
                t.first_response_due_at = resp_due
                t.resolution_due_at = res_due
                if t.status == "waiting_on_customer":
                    t.sla_paused_at = now
                # Generate customer magic link token
                t.customer_token_hash = generate_customer_token(t.id, t.customer_email)
                db.add(t)
            db.commit()
        else:
            # Existing database: backfill password hashes if missing (v2 migration)
            pwd_hash = hash_password(_DEFAULT_PASSWORD)
            agents = db.query(Agent).filter(
                (Agent.password_hash == None) | (Agent.password_hash == "")
            ).all()
            for agent in agents:
                agent.password_hash = pwd_hash
            if agents:
                db.commit()

        # Seed or backfill Customers (v5)
        pwd_hash = hash_password(_DEFAULT_PASSWORD)
        for cust_data in SEED_CUSTOMERS:
            existing = db.query(Customer).filter(Customer.email == cust_data["email"]).first()
            if not existing:
                db.add(Customer(**cust_data, password_hash=pwd_hash, is_active=True))
            elif not existing.password_hash:
                existing.password_hash = pwd_hash
        db.commit()

        # Ensure tickets exist for customer@acmecorp.com
        rahul_tickets = db.query(Ticket).filter(Ticket.customer_email == "customer@acmecorp.com").all()
        if not rahul_tickets:
            now = datetime.now(timezone.utc)
            t1 = Ticket(
                id="INC-0501",
                title="VPN certificate expired on Bangalore gateway",
                description="Unable to connect to internal staging environment since our SSL VPN cert expired.",
                customer_name="Rahul Sharma",
                customer_email="customer@acmecorp.com",
                priority="urgent",
                status="waiting_on_customer",
                sla_paused_at=now,
                created_at=now,
                customer_token_hash=generate_customer_token("INC-0501", "customer@acmecorp.com"),
            )
            resp_due, res_due = compute_ticket_slas(now, t1.priority)
            t1.first_response_due_at = resp_due
            t1.resolution_due_at = res_due
            db.add(t1)

            t2 = Ticket(
                id="INC-0502",
                title="Bulk CSV exports timing out on analytics dashboard",
                description="Exporting Q3 report with >10,000 rows fails with gateway timeout 504.",
                customer_name="Rahul Sharma",
                customer_email="customer@acmecorp.com",
                priority="medium",
                status="in_progress",
                created_at=now,
                customer_token_hash=generate_customer_token("INC-0502", "customer@acmecorp.com"),
            )
            resp_due2, res_due2 = compute_ticket_slas(now, t2.priority)
            t2.first_response_due_at = resp_due2
            t2.resolution_due_at = res_due2
            db.add(t2)
            db.commit()
    finally:
        db.close()
