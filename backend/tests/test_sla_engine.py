"""Automated Verification Test Suite for Working Hours SLA Engine (Stage 4 / INC-0327).

Arvo Systems Requirements:
- Business hours: 09:30 to 18:30 (9 hours = 540 min/day), Monday to Friday.
- Pauses on: Saturdays, Sundays, and Festival Holidays.
- Urgent: 2 working hours (120 min) reply, fix same working day (18:30).
- Medium: 4.5 working hours (270 min) reply, fix within 3 working days (1620 min).
- Small: 1 working day (540 min) reply, fix within 1 working week (2700 min).
- Timer freezes when status is 'waiting_on_customer' and resumes upon customer reply.
- Mid-lifecycle escalation: Recalculates clock dynamically from escalation point.
- Non-repudiation audit logging for escalation and resolution.
"""
import sys
import os
from datetime import datetime, date, timezone, timedelta
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.sla import (
    add_business_minutes,
    calculate_business_minutes_between,
    compute_ticket_slas,
    compute_sla_status,
    is_business_day,
    next_business_start,
)

BASE_URL = "http://localhost:8000/api"
AGENT_MEERA = "a1000001-0000-0000-0000-000000000001"


def create_test_ticket(title: str, priority: str = "urgent"):
    res = requests.post(
        f"{BASE_URL}/tickets",
        json={
            "title": title,
            "description": "Testing Working Hours SLA Engine",
            "customer_name": "Siddharth Verma",
            "customer_email": "siddharth@client.com",
            "priority": priority,
        },
    )
    assert res.status_code == 201, f"Failed to create ticket: {res.text}"
    return res.json()


def test_business_hours_calculations():
    """Unit tests for pure business hours calculation logic."""
    print("\n[TEST 1] Testing Business Hours Calculation Logic...")

    # 1. Normal addition within same day: Monday 10:00 + 60 min -> Monday 11:00
    mon_10am = datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc)  # Monday
    res = add_business_minutes(mon_10am, 60)
    assert res == datetime(2026, 4, 6, 11, 0, tzinfo=timezone.utc), f"Got {res}"
    print("  ✓ Same-day addition within business hours passed.")

    # 2. Friday evening addition: Friday 18:00 + 120 min (30m left Friday, 90m into Monday) -> Monday 11:00
    fri_6pm = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)  # Friday
    res_fri = add_business_minutes(fri_6pm, 120)
    assert res_fri == datetime(2026, 4, 13, 11, 0, tzinfo=timezone.utc), f"Got {res_fri}"
    print("  ✓ Weekend skip (Friday -> Monday 11:00) passed.")

    # 3. Holiday skip: 2026-04-03 is Good Friday. Thursday 18:00 (2026-04-02) + 60 min -> Monday 10:00
    thu_6pm = datetime(2026, 4, 2, 18, 0, tzinfo=timezone.utc)
    res_holiday = add_business_minutes(thu_6pm, 60)
    # Thursday has 30 mins left (18:00 to 18:30), remaining 30 mins should fall on Monday 10:00
    assert res_holiday == datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc), f"Got {res_holiday}"
    print("  ✓ Festival Holiday skip (Good Friday + Weekend -> Monday 10:00) passed.")

    # 4. Off-hours creation: Saturday 14:00 + 60 min -> Monday 10:30
    sat_2pm = datetime(2026, 4, 4, 14, 0, tzinfo=timezone.utc)
    res_weekend = add_business_minutes(sat_2pm, 60)
    assert res_weekend == datetime(2026, 4, 6, 10, 30, tzinfo=timezone.utc), f"Got {res_weekend}"
    print("  ✓ Off-hours start advancement passed.")


def test_ticket_creation_sets_sla_deadlines():
    """Verify that creating tickets of each priority sets proper first response and resolution deadlines."""
    print("\n[TEST 2] Testing Ticket SLA Deadlines by Priority...")

    # Urgent ticket
    urgent = create_test_ticket("Urgent SLA Test", priority="urgent")
    assert urgent["first_response_due_at"] is not None
    assert urgent["resolution_due_at"] is not None
    assert urgent["sla_status"] is not None
    assert urgent["sla_status"]["is_overdue"] is False
    assert "Due in" in urgent["sla_status"]["label"]
    print(f"  ✓ Urgent ticket SLA initialized: {urgent['sla_status']['label']}")

    # Medium ticket
    medium = create_test_ticket("Medium SLA Test", priority="medium")
    assert medium["first_response_due_at"] is not None
    assert medium["resolution_due_at"] is not None
    print(f"  ✓ Medium ticket SLA initialized: {medium['sla_status']['label']}")

    # Small ticket
    small = create_test_ticket("Small SLA Test", priority="small")
    assert small["first_response_due_at"] is not None
    assert small["resolution_due_at"] is not None
    print(f"  ✓ Small ticket SLA initialized: {small['sla_status']['label']}")


def test_sla_pause_and_resume_lifecycle():
    """Verify SLA pauses when ticket is waiting on customer and resumes upon customer reply."""
    print("\n[TEST 3] Testing SLA Pause / Resume on Customer Inactivity...")

    ticket = create_test_ticket("Pause/Resume SLA Test", priority="medium")
    ticket_id = ticket["id"]

    # 1. Agent sends public reply -> Ticket moves to 'waiting_on_customer' & SLA pauses
    reply_res = requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={
            "content": "Can you please send your log files?",
            "is_private": False,
            "sender_type": "agent",
            "sender_id": AGENT_MEERA,
            "sender_name": "Meera",
        },
    )
    assert reply_res.status_code == 201

    updated_ticket = requests.get(f"{BASE_URL}/tickets/{ticket_id}").json()
    assert updated_ticket["status"] == "waiting_on_customer"
    assert updated_ticket["sla_paused_at"] is not None
    assert updated_ticket["sla_status"]["state"] == "paused"
    assert updated_ticket["sla_status"]["is_paused"] is True
    print("  ✓ Ticket status moved to waiting_on_customer, SLA paused successfully.")

    # 2. Customer replies back -> Ticket moves to 'in_progress', SLA unpauses
    cust_res = requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={
            "content": "Here are the requested log files.",
            "is_private": False,
            "sender_type": "customer",
            "sender_name": "Siddharth Verma",
        },
    )
    assert cust_res.status_code == 201

    resumed_ticket = requests.get(f"{BASE_URL}/tickets/{ticket_id}").json()
    assert resumed_ticket["status"] == "in_progress"
    assert resumed_ticket["sla_paused_at"] is None
    assert resumed_ticket["sla_status"]["is_paused"] is False
    print("  ✓ Customer replied, ticket moved back to in_progress and SLA resumed.")


def test_priority_escalation_recalculates_sla_and_audits():
    """Verify mid-lifecycle priority change recalculates SLA from escalation time and audits."""
    print("\n[TEST 4] Testing Mid-Lifecycle Priority Escalation...")

    ticket = create_test_ticket("Escalation SLA Test", priority="small")
    ticket_id = ticket["id"]
    initial_resolution_due = ticket["resolution_due_at"]

    # Escalate to Urgent
    patch_res = requests.patch(
        f"{BASE_URL}/tickets/{ticket_id}/priority",
        json={"priority": "urgent", "agent_id": AGENT_MEERA},
    )
    assert patch_res.status_code == 200, f"Escalation failed: {patch_res.text}"
    escalated = patch_res.json()
    assert escalated["priority"] == "urgent"
    assert escalated["resolution_due_at"] != initial_resolution_due
    print(f"  ✓ Priority escalated to urgent, new resolution deadline: {escalated['resolution_due_at']}")

    # Check audit log contains PRIORITY_CHANGED
    logs = requests.get(f"{BASE_URL}/tickets/{ticket_id}/audit").json()
    actions = [l["action"] for l in logs]
    assert "PRIORITY_CHANGED" in actions
    audit_entry = next(l for l in logs if l["action"] == "PRIORITY_CHANGED")
    assert audit_entry["actor_name"] == "Meera"
    assert audit_entry["details"]["previous_priority"] == "small"
    assert audit_entry["details"]["new_priority"] == "urgent"
    print("  ✓ PRIORITY_CHANGED correctly recorded in immutable audit log.")


def test_ticket_resolution_freezes_sla():
    """Verify resolving ticket marks it done, records resolved_at, sets SLA completed, and audits."""
    print("\n[TEST 5] Testing Ticket Resolution...")

    ticket = create_test_ticket("Resolve SLA Test", priority="urgent")
    ticket_id = ticket["id"]

    # Claim first
    requests.post(f"{BASE_URL}/tickets/{ticket_id}/claim", json={"agent_id": AGENT_MEERA})

    # Resolve ticket
    res = requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/resolve",
        json={"agent_id": AGENT_MEERA},
    )
    assert res.status_code == 200, f"Resolution failed: {res.text}"
    resolved = res.json()
    assert resolved["status"] == "done"
    assert resolved["resolved_at"] is not None
    assert resolved["sla_status"]["state"] == "completed"
    assert resolved["sla_status"]["label"] == "Resolved"
    print("  ✓ Ticket resolved successfully with SLA state 'completed'.")

    # Check audit log contains TICKET_RESOLVED
    logs = requests.get(f"{BASE_URL}/tickets/{ticket_id}/audit").json()
    actions = [l["action"] for l in logs]
    assert "TICKET_RESOLVED" in actions
    audit_entry = next(l for l in logs if l["action"] == "TICKET_RESOLVED")
    assert audit_entry["actor_name"] == "Meera"
    assert audit_entry["details"]["status"] == "done"
    print("  ✓ TICKET_RESOLVED correctly recorded in immutable audit log.")


if __name__ == "__main__":
    test_business_hours_calculations()
    test_ticket_creation_sets_sla_deadlines()
    test_sla_pause_and_resume_lifecycle()
    test_priority_escalation_recalculates_sla_and_audits()
    test_ticket_resolution_freezes_sla()
    print("\n✅ ALL STAGE 4 SLA ENGINE TESTS PASSED SUCCESSFULLY!")
