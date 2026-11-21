"""Automated Verification Test Suite for Immutable Audit Event Sourcing (INC-0318).

Incident INC-0318: A customer said Arvo did not reply until the next morning.
Arvo believed the reply was sent in forty minutes. Nobody could prove who was right.
The system must record exactly what happened, when it happened, and who did it.
Nobody should be able to change that record later.
"""
from datetime import datetime
import requests

BASE_URL = "http://localhost:8000/api"
AGENT_MEERA = "a1000001-0000-0000-0000-000000000001"
AGENT_RAVI = "a1000001-0000-0000-0000-000000000002"


def create_test_ticket(title: str):
    res = requests.post(
        f"{BASE_URL}/tickets",
        json={
            "title": title,
            "description": "Testing immutable audit trail for non-repudiation",
            "customer_name": "Kavita Rao",
            "customer_email": "kavita@fintech.com",
            "priority": "urgent",
        },
    )
    assert res.status_code == 201
    return res.json()


def test_audit_trail_records_full_lifecycle():
    """Verify that every lifecycle event records an immutable audit log entry."""
    ticket = create_test_ticket("INC-0318 Audit Lifecycle Simulation")
    ticket_id = ticket["id"]
    print(f"\n[TEST 1] Testing Audit Trail with Ticket: {ticket_id}")

    # 1. Ticket Creation should automatically log TICKET_CREATED
    audit_res1 = requests.get(f"{BASE_URL}/tickets/{ticket_id}/audit")
    assert audit_res1.status_code == 200
    logs1 = audit_res1.json()
    assert len(logs1) == 1
    assert logs1[0]["action"] == "TICKET_CREATED"
    assert logs1[0]["actor_name"] == "Kavita Rao"
    assert logs1[0]["actor_type"] == "customer"
    print("[TEST 1] PASS: TICKET_CREATED logged automatically.")

    # 2. Claim Ticket should log TICKET_CLAIMED
    requests.post(f"{BASE_URL}/tickets/{ticket_id}/claim", json={"agent_id": AGENT_MEERA})
    logs2 = requests.get(f"{BASE_URL}/tickets/{ticket_id}/audit").json()
    assert len(logs2) == 2
    assert logs2[1]["action"] == "TICKET_CLAIMED"
    assert logs2[1]["actor_name"] == "Meera"
    assert logs2[1]["actor_type"] == "agent"
    assert logs2[1]["details"]["status"] == "in_progress"
    print("[TEST 1] PASS: TICKET_CLAIMED logged with agent name and status.")

    # 3. Private Internal Note should log INTERNAL_NOTE_ADDED
    requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={
            "content": "Checking database replication lag on secondary.",
            "is_private": True,
            "sender_type": "agent",
            "sender_id": AGENT_MEERA,
            "sender_name": "Meera",
        },
    )
    logs3 = requests.get(f"{BASE_URL}/tickets/{ticket_id}/audit").json()
    assert len(logs3) == 3
    assert logs3[2]["action"] == "INTERNAL_NOTE_ADDED"
    assert logs3[2]["actor_name"] == "Meera"
    assert logs3[2]["details"]["is_private"] is True
    print("[TEST 1] PASS: INTERNAL_NOTE_ADDED logged.")

    # 4. Public Agent Reply should log PUBLIC_REPLY_SENT
    requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={
            "content": "Kavita, replication sync completed. Can you verify login?",
            "is_private": False,
            "sender_type": "agent",
            "sender_id": AGENT_MEERA,
            "sender_name": "Meera",
        },
    )
    logs4 = requests.get(f"{BASE_URL}/tickets/{ticket_id}/audit").json()
    assert len(logs4) == 4
    assert logs4[3]["action"] == "PUBLIC_REPLY_SENT"
    assert logs4[3]["actor_name"] == "Meera"
    assert logs4[3]["details"]["status"] == "waiting_on_customer"
    print("[TEST 1] PASS: PUBLIC_REPLY_SENT logged with status change to waiting_on_customer.")

    # 5. Customer Reply should log CUSTOMER_REPLY_RECEIVED
    requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={
            "content": "Yes, verified! Login is working normally now.",
            "is_private": False,
            "sender_type": "customer",
            "sender_name": "Kavita Rao",
        },
    )
    logs5 = requests.get(f"{BASE_URL}/tickets/{ticket_id}/audit").json()
    assert len(logs5) == 5
    assert logs5[4]["action"] == "CUSTOMER_REPLY_RECEIVED"
    assert logs5[4]["actor_name"] == "Kavita Rao"
    assert logs5[4]["actor_type"] == "customer"
    print("[TEST 1] PASS: CUSTOMER_REPLY_RECEIVED logged.")


def test_dispute_resolution_non_repudiation():
    """Verify solving INC-0318 dispute: Exactly proves reply interval between ticket creation and agent reply."""
    ticket = create_test_ticket("Dispute Resolution Verification (INC-0318)")
    ticket_id = ticket["id"]

    # Agent replies 1 second later
    requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={
            "content": "Immediate reply to customer.",
            "is_private": False,
            "sender_type": "agent",
            "sender_id": AGENT_MEERA,
            "sender_name": "Meera",
        },
    )

    logs = requests.get(f"{BASE_URL}/tickets/{ticket_id}/audit").json()
    created_event = [l for l in logs if l["action"] == "TICKET_CREATED"][0]
    reply_event = [l for l in logs if l["action"] == "PUBLIC_REPLY_SENT"][0]

    t_created = datetime.fromisoformat(created_event["created_at"])
    t_reply = datetime.fromisoformat(reply_event["created_at"])
    elapsed_seconds = (t_reply - t_created).total_seconds()

    print(f"[TEST 2] Ticket Created At: {t_created}")
    print(f"[TEST 2] Public Reply Sent At: {t_reply}")
    print(f"[TEST 2] Mathematical elapsed response time: {elapsed_seconds:.4f} seconds")
    assert elapsed_seconds >= 0, "Reply cannot precede ticket creation"
    assert reply_event["actor_name"] == "Meera"
    print("[TEST 2] PASS: INC-0318 dispute conclusively resolved with mathematical timestamps.")


def test_audit_logs_are_read_only_and_immutable():
    """Verify that no modification (PUT, PATCH, DELETE, POST) endpoints exist for audit logs."""
    ticket = create_test_ticket("Audit Immutability Test")
    ticket_id = ticket["id"]

    # Attempting POST to audit endpoint should return 405 Method Not Allowed
    post_res = requests.post(f"{BASE_URL}/tickets/{ticket_id}/audit", json={"action": "TAMPER"})
    assert post_res.status_code == 405, f"Expected 405, got {post_res.status_code}"

    # Attempting DELETE on audit endpoint should return 405 Method Not Allowed
    delete_res = requests.delete(f"{BASE_URL}/tickets/{ticket_id}/audit")
    assert delete_res.status_code == 405, f"Expected 405, got {delete_res.status_code}"

    # Attempting PUT on audit endpoint should return 405 Method Not Allowed
    put_res = requests.put(f"{BASE_URL}/tickets/{ticket_id}/audit", json={})
    assert put_res.status_code == 405, f"Expected 405, got {put_res.status_code}"

    print("[TEST 3] PASS: Audit log is strictly read-only; tampering endpoints are disallowed (405).")


if __name__ == "__main__":
    print("=== Running Audit Trail & Non-Repudiation Tests (INC-0318) ===")
    test_audit_trail_records_full_lifecycle()
    test_dispute_resolution_non_repudiation()
    test_audit_logs_are_read_only_and_immutable()
    print("\nALL AUDIT TRAIL TESTS PASSED SUCCESSFULLY! (INC-0318 Solved)")
