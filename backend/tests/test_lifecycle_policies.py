"""Automated Verification Test Suite for Lifecycle Inactivity & Reopening Policies (Stage 5 / REQ-SLA-04 & REQ-SLA-05).

Policies verified:
- REQ-SLA-05: Reopen Window Guard:
  - Allowed within 7 calendar days of resolution/closure.
  - Strictly rejected after 7 calendar days with HTTP 400:
    "Tickets closed more than 1 week ago cannot be reopened. Please submit a new ticket."
  - Non-repudiation audit logging for TICKET_REOPENED.
- REQ-SLA-04: Auto-Close Inactive Tickets:
  - Tickets in 'waiting_on_customer' for >= 5 working days (45 hours = 2,700 business minutes)
    automatically transition to 'closed'.
  - System logs AUTO_CLOSED audit event.
"""
import sys
import os
from datetime import datetime, timezone, timedelta
import requests
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.lifecycle import can_reopen_ticket, should_auto_close

BASE_URL = "http://localhost:8000/api"
AGENT_MEERA = "a1000001-0000-0000-0000-000000000001"
DB_PATH = "frontdesk.db"


def create_test_ticket(title: str, priority: str = "medium"):
    res = requests.post(
        f"{BASE_URL}/tickets",
        json={
            "title": title,
            "description": "Testing Lifecycle Policies",
            "customer_name": "Aarav Sharma",
            "customer_email": "aarav@enterprise.com",
            "priority": priority,
        },
    )
    assert res.status_code == 201, f"Failed to create ticket: {res.text}"
    return res.json()


def test_reopen_within_seven_days_allowed():
    """Verify that a ticket resolved recently (< 7 calendar days) can be reopened."""
    print("\n[TEST 1] Testing Reopen Within 7 Days Window (Allowed)...")
    ticket = create_test_ticket("Reopen Recent Ticket")
    ticket_id = ticket["id"]

    # Claim & Resolve ticket
    requests.post(f"{BASE_URL}/tickets/{ticket_id}/claim", json={"agent_id": AGENT_MEERA})
    res_resolve = requests.post(f"{BASE_URL}/tickets/{ticket_id}/resolve", json={"agent_id": AGENT_MEERA})
    assert res_resolve.status_code == 200
    assert res_resolve.json()["status"] == "done"

    # Reopen ticket within 7 days
    res_reopen = requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/reopen",
        json={"agent_id": AGENT_MEERA, "reason": "Customer reported issue persists"},
    )
    assert res_reopen.status_code == 200, f"Expected 200, got: {res_reopen.status_code} - {res_reopen.text}"
    reopened = res_reopen.json()
    assert reopened["status"] == "in_progress"
    assert reopened["resolved_at"] is None
    print(f"  ✓ Ticket {ticket_id} reopened successfully to status: {reopened['status']}")

    # Verify TICKET_REOPENED audit event
    logs = requests.get(f"{BASE_URL}/tickets/{ticket_id}/audit").json()
    actions = [l["action"] for l in logs]
    assert "TICKET_REOPENED" in actions
    audit_entry = next(l for l in logs if l["action"] == "TICKET_REOPENED")
    assert audit_entry["actor_name"] == "Meera"
    assert audit_entry["details"]["previous_status"] == "done"
    print("  ✓ TICKET_REOPENED logged in immutable audit trail.")


def test_reopen_after_seven_days_rejected():
    """Verify REQ-SLA-05: Tickets closed > 7 calendar days ago cannot be reopened (HTTP 400)."""
    print("\n[TEST 2] Testing Reopen Guard After 7 Days (Strictly Rejected)...")
    ticket = create_test_ticket("Reopen Expired Ticket")
    ticket_id = ticket["id"]

    # Claim & Resolve
    requests.post(f"{BASE_URL}/tickets/{ticket_id}/claim", json={"agent_id": AGENT_MEERA})
    requests.post(f"{BASE_URL}/tickets/{ticket_id}/resolve", json={"agent_id": AGENT_MEERA})

    # Simulate resolved 10 days ago directly in SQLite
    ten_days_ago = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE tickets SET resolved_at = ? WHERE id = ?", (ten_days_ago, ticket_id))
    conn.commit()
    conn.close()

    # Attempt to reopen
    res_reopen = requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/reopen",
        json={"agent_id": AGENT_MEERA, "reason": "Customer recontacted late"},
    )
    assert res_reopen.status_code == 400, f"Expected 400, got: {res_reopen.status_code}"
    error_detail = res_reopen.json().get("detail", "")
    print(f"  ✓ HTTP 400 received with message: '{error_detail}'")
    assert "Tickets closed more than 1 week ago cannot be reopened. Please submit a new ticket." in error_detail

    # Verify ticket status remained unchanged
    ticket_state = requests.get(f"{BASE_URL}/tickets/{ticket_id}").json()
    assert ticket_state["status"] == "done"
    print("  ✓ Ticket status remained unchanged as 'done'.")


def test_reopen_open_ticket_rejected():
    """Verify that active (open/in_progress) tickets cannot be reopened."""
    print("\n[TEST 3] Testing Reopen on Active Ticket (Rejected)...")
    ticket = create_test_ticket("Active Ticket Reopen")
    ticket_id = ticket["id"]

    res = requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/reopen",
        json={"agent_id": AGENT_MEERA},
    )
    assert res.status_code == 400
    assert "Only resolved or closed tickets can be reopened" in res.json().get("detail", "")
    print("  ✓ Rejecting reopen on active ticket passed.")


def test_auto_close_inactivity_policy():
    """Verify REQ-SLA-04: Tickets in waiting_on_customer >= 5 working days auto-close."""
    print("\n[TEST 4] Testing Auto-Close Inactivity Policy (5 Working Days)...")
    ticket = create_test_ticket("Auto-Close Inactivity Test")
    ticket_id = ticket["id"]

    # Agent replies publicly -> moves to 'waiting_on_customer'
    requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={
            "content": "Awaiting customer confirmation.",
            "is_private": False,
            "sender_type": "agent",
            "sender_id": AGENT_MEERA,
            "sender_name": "Meera",
        },
    )
    ticket_waiting = requests.get(f"{BASE_URL}/tickets/{ticket_id}").json()
    assert ticket_waiting["status"] == "waiting_on_customer"

    # Case A: Inactive for only 2 days (not eligible for auto-close)
    two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE tickets SET sla_paused_at = ? WHERE id = ?", (two_days_ago, ticket_id))
    conn.commit()
    conn.close()

    res_check1 = requests.post(f"{BASE_URL}/tickets/auto-close")
    assert res_check1.status_code == 200
    ticket_after_check1 = requests.get(f"{BASE_URL}/tickets/{ticket_id}").json()
    assert ticket_after_check1["status"] == "waiting_on_customer"
    print("  ✓ Ticket with < 5 working days inactivity was NOT auto-closed.")

    # Case B: Inactive for 10 calendar days (which guarantees >= 5 working days / 45 business hours)
    ten_days_ago = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE tickets SET sla_paused_at = ? WHERE id = ?", (ten_days_ago, ticket_id))
    conn.commit()
    conn.close()

    res_check2 = requests.post(f"{BASE_URL}/tickets/auto-close")
    assert res_check2.status_code == 200
    auto_closed_list = res_check2.json()
    auto_closed_ids = [t["id"] for t in auto_closed_list]
    assert ticket_id in auto_closed_ids

    # Verify status in database
    ticket_final = requests.get(f"{BASE_URL}/tickets/{ticket_id}").json()
    assert ticket_final["status"] == "closed"
    assert ticket_final["closed_at"] is not None
    print(f"  ✓ Ticket {ticket_id} automatically transitioned to 'closed' on {ticket_final['closed_at']}")

    # Verify AUTO_CLOSED audit log entry
    logs = requests.get(f"{BASE_URL}/tickets/{ticket_id}/audit").json()
    actions = [l["action"] for l in logs]
    assert "AUTO_CLOSED" in actions
    audit_entry = next(l for l in logs if l["action"] == "AUTO_CLOSED")
    assert audit_entry["actor_name"] == "System Automator"
    assert audit_entry["actor_type"] == "system"
    print("  ✓ AUTO_CLOSED recorded in immutable audit trail by System Automator.")


if __name__ == "__main__":
    test_reopen_within_seven_days_allowed()
    test_reopen_after_seven_days_rejected()
    test_reopen_open_ticket_rejected()
    test_auto_close_inactivity_policy()
    print("\n✅ ALL STAGE 5 LIFECYCLE POLICY TESTS PASSED SUCCESSFULLY!")
