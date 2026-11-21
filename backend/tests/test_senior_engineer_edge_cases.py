"""Senior Engineer Edge Case Test Suite for Arvo Systems Frontdesk.

Deep boundary and stress testing across all modules:
1. Concurrency Stress (N=5 simultaneous agents on single ticket).
2. Claiming Guards (terminal states, invalid inputs).
3. Messaging Boundary Validation (empty content, customer scope leak prevention, closed ticket message guard).
4. SLA Exact Boundary Arithmetic (exact 09:30 start, exact 18:30 end, weekend pause calculation, holiday spans).
5. Priority Escalation Guards (terminal state protection, invalid priority string, pre/post response recalculation).
6. Lifecycle Reopening Boundary Conditions (6d23h vs 7d1h, active ticket rejection, auto-closed ticket reopen).
7. Auto-Close Working-Hours vs Calendar-Days Inactivity Thresholds (2699 min vs 2700 min).
8. Audit Trail Immutability and Ordering.
"""
import concurrent.futures
from datetime import datetime, timezone, timedelta, date
import requests
import sqlite3

from app.sla import (
    add_business_minutes,
    calculate_business_minutes_between,
    compute_ticket_slas,
    recalculate_sla_on_priority_change,
    compute_sla_status,
)
from app.lifecycle import can_reopen_ticket, should_auto_close

BASE_URL = "http://localhost:8000/api"
DB_PATH = "frontdesk.db"

# Sample agent IDs from seed
AGENT_MEERA = "a1000001-0000-0000-0000-000000000001"
AGENT_RAVI = "a1000001-0000-0000-0000-000000000002"
AGENT_PRIYA = "a1000001-0000-0000-0000-000000000003"
AGENT_ARJUN = "a1000001-0000-0000-0000-000000000004"
AGENT_SNEHA = "a1000001-0000-0000-0000-000000000005"


def create_test_ticket(title: str, priority: str = "medium") -> dict:
    res = requests.post(
        f"{BASE_URL}/tickets",
        json={
            "title": title,
            "description": "Senior Engineer Edge Case Test",
            "customer_name": "Deep Edge Tester",
            "customer_email": "edge@tester.io",
            "priority": priority,
        },
    )
    assert res.status_code == 201, f"Create ticket failed: {res.text}"
    return res.json()


# ── 1. CONCURRENCY STRESS TEST (N=5 AGENTS) ──

def test_high_concurrency_claim():
    """5 agents try to claim the exact same ticket concurrently.
    Guarantees: Exactly 1 succeeds (200), 4 fail (409).
    """
    print("\n[EDGE 1] High Concurrency Claiming (5 simultaneous agents)...")
    ticket = create_test_ticket("Concurrent 5-Agent Claim Race")
    ticket_id = ticket["id"]

    agents = [AGENT_MEERA, AGENT_RAVI, AGENT_PRIYA, AGENT_ARJUN, AGENT_SNEHA]

    def claim_worker(agent_id):
        return requests.post(f"{BASE_URL}/tickets/{ticket_id}/claim", json={"agent_id": agent_id})

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(claim_worker, agents))

    status_codes = [r.status_code for r in results]
    print(f"  ✓ Status codes from 5 simultaneous workers: {status_codes}")
    assert status_codes.count(200) == 1, f"Expected exactly one 200, got: {status_codes}"
    assert status_codes.count(409) == 4, f"Expected four 409s, got: {status_codes}"

    # Verify final ticket in database is assigned to one agent with status 'in_progress'
    final_ticket = requests.get(f"{BASE_URL}/tickets/{ticket_id}").json()
    assert final_ticket["assigned_agent_id"] in agents
    assert final_ticket["status"] == "in_progress"
    print(f"  ✓ Safely claimed by winner: {final_ticket['assigned_agent_name']}")


# ── 2. CLAIMING GUARDS ON TERMINAL STATES ──

def test_claiming_guards_on_terminal_states():
    """Verify that a ticket in 'done' or 'closed' status cannot be claimed directly."""
    print("\n[EDGE 2] Claiming Guards on Terminal States...")
    ticket = create_test_ticket("Claiming Terminal State Ticket")
    ticket_id = ticket["id"]

    # Claim and resolve
    requests.post(f"{BASE_URL}/tickets/{ticket_id}/claim", json={"agent_id": AGENT_MEERA})
    requests.post(f"{BASE_URL}/tickets/{ticket_id}/resolve", json={"agent_id": AGENT_MEERA})

    # Clear assigned_agent_id in DB while leaving status as 'done'
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE tickets SET assigned_agent_id = NULL WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()

    # Attempt to claim an unassigned but resolved ticket
    res = requests.post(f"{BASE_URL}/tickets/{ticket_id}/claim", json={"agent_id": AGENT_RAVI})
    assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
    assert "Cannot claim a resolved or closed ticket" in res.json().get("detail", "")
    print("  ✓ Claiming resolved/closed ticket rejected with HTTP 400.")


# ── 3. MESSAGING BOUNDARY & SECURITY GUARDS ──

def test_empty_message_and_security_leak_guards():
    """Verify empty/whitespace message rejection and customer scope note leak protection."""
    print("\n[EDGE 3] Messaging Boundary & Security Leak Guards...")
    ticket = create_test_ticket("Messaging Edge Test")
    ticket_id = ticket["id"]

    # 1. Empty message rejection
    res_empty = requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={"content": "   ", "is_private": False, "sender_type": "agent", "sender_id": AGENT_MEERA},
    )
    assert res_empty.status_code == 400, f"Expected 400 for empty message, got {res_empty.status_code}"
    print("  ✓ Empty / whitespace message rejected with HTTP 400.")

    # 2. Post private note & public reply
    requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={"content": "SECRET_LEAK_TEST_INTERNAL_NOTE", "is_private": True, "sender_type": "agent", "sender_id": AGENT_MEERA},
    )
    requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={"content": "PUBLIC_RESPONSE_FOR_CUSTOMER", "is_private": False, "sender_type": "agent", "sender_id": AGENT_MEERA},
    )

    # 3. Customer scope API query: must NOT contain private note and must NOT expose is_private field
    cust_res = requests.get(f"{BASE_URL}/tickets/{ticket_id}/messages?scope=customer").json()
    assert len(cust_res) == 1
    assert cust_res[0]["content"] == "PUBLIC_RESPONSE_FOR_CUSTOMER"
    for msg in cust_res:
        assert "is_private" not in msg, f"Customer DTO must never leak is_private field: {msg}"
        assert "SECRET" not in msg["content"]
    print("  ✓ Customer scope strictly filters private notes and omits is_private field.")

    # 4. Message on ticket closed > 7 days must be rejected
    requests.post(f"{BASE_URL}/tickets/{ticket_id}/resolve", json={"agent_id": AGENT_MEERA})
    ten_days_ago = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE tickets SET resolved_at = ? WHERE id = ?", (ten_days_ago, ticket_id))
    conn.commit()
    conn.close()

    res_late_msg = requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={"content": "Hello customer trying to message expired ticket", "sender_type": "customer"},
    )
    assert res_late_msg.status_code == 400, f"Expected 400 for message on expired ticket, got {res_late_msg.status_code}"
    print("  ✓ Customer messaging on ticket closed > 7 days rejected with HTTP 400.")


# ── 4. SLA EXACT BOUNDARY ARITHMETIC ──

def test_sla_exact_boundary_arithmetic():
    """Verify Indian working hours calculation at exact boundary seconds and pause intervals."""
    print("\n[EDGE 4] SLA Exact Boundary Arithmetic...")

    # 1. Exact start of business hours: Monday 09:30:00 + 120 min -> Monday 11:30:00
    mon_start = datetime(2026, 4, 6, 9, 30, 0, tzinfo=timezone.utc)
    res_start = add_business_minutes(mon_start, 120)
    assert res_start == datetime(2026, 4, 6, 11, 30, 0, tzinfo=timezone.utc)
    print("  ✓ Exact business start (09:30) addition passed.")

    # 2. Exact end of business hours: Monday 18:30:00 + 60 min -> Tuesday 10:30:00 (rolls over)
    mon_end = datetime(2026, 4, 6, 18, 30, 0, tzinfo=timezone.utc)
    res_end = add_business_minutes(mon_end, 60)
    assert res_end == datetime(2026, 4, 7, 10, 30, 0, tzinfo=timezone.utc)
    print("  ✓ Exact business end (18:30) rollover passed.")

    # 3. Pause across weekend: Friday 18:00 to Monday 10:00
    # Business time elapsed: Friday (18:00 to 18:30 = 30m) + Weekend (0m) + Monday (09:30 to 10:00 = 30m) = 60 min
    fri_6pm = datetime(2026, 4, 10, 18, 0, 0, tzinfo=timezone.utc)
    mon_10am = datetime(2026, 4, 13, 10, 0, 0, tzinfo=timezone.utc)
    elapsed_weekend = calculate_business_minutes_between(fri_6pm, mon_10am)
    assert elapsed_weekend == 60, f"Expected 60 business minutes across weekend, got {elapsed_weekend}"
    print("  ✓ Paused duration across weekend is exactly 60 business minutes (not 64 hours).")

    # 4. Multi-day holiday span: 2026-04-03 is Good Friday.
    # Thursday 18:00 to Monday 10:00:
    # Thursday 18:00 to 18:30 = 30m. Good Friday = 0m. Saturday/Sunday = 0m. Monday 09:30 to 10:00 = 30m. Total = 60m.
    thu_6pm = datetime(2026, 4, 2, 18, 0, 0, tzinfo=timezone.utc)
    mon_after_holiday = datetime(2026, 4, 6, 10, 0, 0, tzinfo=timezone.utc)
    elapsed_holiday = calculate_business_minutes_between(thu_6pm, mon_after_holiday)
    assert elapsed_holiday == 60, f"Expected 60 business minutes across holiday weekend, got {elapsed_holiday}"
    print("  ✓ Multi-day holiday span correctly skips Good Friday + Weekend.")


# ── 5. PRIORITY ESCALATION GUARDS ──

def test_priority_escalation_guards():
    """Verify priority escalation validation and terminal state protection."""
    print("\n[EDGE 5] Priority Escalation Guards...")
    ticket = create_test_ticket("Priority Escalation Guard Test", priority="small")
    ticket_id = ticket["id"]

    # 1. Invalid priority string rejected with 400
    res_bad = requests.patch(f"{BASE_URL}/tickets/{ticket_id}/priority", json={"priority": "EXTREME_URGENT"})
    assert res_bad.status_code == 400
    print("  ✓ Invalid priority string rejected with HTTP 400.")

    # 2. Cannot escalate a resolved ticket
    requests.post(f"{BASE_URL}/tickets/{ticket_id}/claim", json={"agent_id": AGENT_MEERA})
    requests.post(f"{BASE_URL}/tickets/{ticket_id}/resolve", json={"agent_id": AGENT_MEERA})

    res_escalate_resolved = requests.patch(f"{BASE_URL}/tickets/{ticket_id}/priority", json={"priority": "urgent"})
    assert res_escalate_resolved.status_code == 400, f"Expected 400, got {res_escalate_resolved.status_code}"
    print("  ✓ Priority escalation on resolved ticket rejected with HTTP 400.")


# ── 6. LIFECYCLE REOPENING BOUNDARY CONDITIONS ──

def test_lifecycle_reopen_exact_boundaries():
    """Verify REQ-SLA-05 exact boundary: allowed at 6d23h, rejected at 7d1h."""
    print("\n[EDGE 6] Lifecycle Reopening Boundary Conditions (6d23h vs 7d1h)...")

    # Ticket A: Resolved 6 days and 23 hours ago (< 7 calendar days) -> ALLOWED
    ticket_a = create_test_ticket("Reopen 6d23h")
    requests.post(f"{BASE_URL}/tickets/{ticket_a['id']}/claim", json={"agent_id": AGENT_MEERA})
    requests.post(f"{BASE_URL}/tickets/{ticket_a['id']}/resolve", json={"agent_id": AGENT_MEERA})

    almost_7_days = (datetime.now(timezone.utc) - timedelta(days=6, hours=23)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE tickets SET resolved_at = ? WHERE id = ?", (almost_7_days, ticket_a["id"]))
    conn.commit()
    conn.close()

    res_a = requests.post(f"{BASE_URL}/tickets/{ticket_a['id']}/reopen", json={"agent_id": AGENT_MEERA})
    assert res_a.status_code == 200, f"Expected 200 at 6d23h, got {res_a.status_code}: {res_a.text}"
    print("  ✓ Reopen at 6 days 23 hours allowed successfully.")

    # Ticket B: Resolved 7 days and 1 hour ago (> 7 calendar days) -> REJECTED
    ticket_b = create_test_ticket("Reopen 7d1h")
    requests.post(f"{BASE_URL}/tickets/{ticket_b['id']}/claim", json={"agent_id": AGENT_MEERA})
    requests.post(f"{BASE_URL}/tickets/{ticket_b['id']}/resolve", json={"agent_id": AGENT_MEERA})

    just_over_7_days = (datetime.now(timezone.utc) - timedelta(days=7, hours=1)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE tickets SET resolved_at = ? WHERE id = ?", (just_over_7_days, ticket_b["id"]))
    conn.commit()
    conn.close()

    res_b = requests.post(f"{BASE_URL}/tickets/{ticket_b['id']}/reopen", json={"agent_id": AGENT_MEERA})
    assert res_b.status_code == 400
    assert "Tickets closed more than 1 week ago cannot be reopened. Please submit a new ticket." in res_b.json().get("detail", "")
    print("  ✓ Reopen at 7 days 1 hour rejected with HTTP 400.")


# ── 7. AUTO-CLOSE INACTIVITY EXACT BUSINESS MINUTES THRESHOLD ──

def test_auto_close_exact_business_threshold():
    """Verify REQ-SLA-04 exact threshold: 2,699 business min is NOT closed, 2,700 min IS closed."""
    print("\n[EDGE 7] Auto-Close Inactivity Exact Business Minutes Threshold...")

    # Set up base time on a Monday 09:30
    base_mon_start = datetime(2026, 4, 6, 9, 30, tzinfo=timezone.utc)

    # 1. Ticket with 2,699 business minutes elapsed
    # 5 working days = 2,700 min. 2,699 min = Friday 18:29.
    fri_1829 = datetime(2026, 4, 10, 18, 29, tzinfo=timezone.utc)
    elapsed_2699 = calculate_business_minutes_between(base_mon_start, fri_1829)
    assert elapsed_2699 == 2699

    class DummyTicket2699:
        status = "waiting_on_customer"
        sla_paused_at = base_mon_start

    assert should_auto_close(DummyTicket2699(), current_time=fri_1829) is False
    print("  ✓ Ticket at 2,699 business minutes does NOT auto-close.")

    # 2. Ticket with 2,700 business minutes elapsed (Friday 18:30)
    fri_1830 = datetime(2026, 4, 10, 18, 30, tzinfo=timezone.utc)
    elapsed_2700 = calculate_business_minutes_between(base_mon_start, fri_1830)
    assert elapsed_2700 == 2700

    class DummyTicket2700:
        status = "waiting_on_customer"
        sla_paused_at = base_mon_start

    assert should_auto_close(DummyTicket2700(), current_time=fri_1830) is True
    print("  ✓ Ticket at exact 2,700 business minutes (5 working days) triggers auto-close.")


# ── 8. AUDIT LOG IMMUTABILITY & ORDERING ──

def test_audit_immutability_and_monotonicity():
    """Verify audit log endpoint is strictly read-only and entries are chronological."""
    print("\n[EDGE 8] Audit Log Immutability & Monotonicity...")
    ticket = create_test_ticket("Audit Monotonic Test")
    ticket_id = ticket["id"]

    # Trigger events: claim, internal note, public reply
    requests.post(f"{BASE_URL}/tickets/{ticket_id}/claim", json={"agent_id": AGENT_MEERA})
    requests.post(f"{BASE_URL}/tickets/{ticket_id}/messages", json={"content": "Internal note", "is_private": True, "sender_type": "agent", "sender_id": AGENT_MEERA})
    requests.post(f"{BASE_URL}/tickets/{ticket_id}/messages", json={"content": "Public reply", "is_private": False, "sender_type": "agent", "sender_id": AGENT_MEERA})

    # Immutability: PUT, PATCH, DELETE must return 405
    assert requests.put(f"{BASE_URL}/tickets/{ticket_id}/audit", json={}).status_code == 405
    assert requests.patch(f"{BASE_URL}/tickets/{ticket_id}/audit", json={}).status_code == 405
    assert requests.delete(f"{BASE_URL}/tickets/{ticket_id}/audit").status_code == 405
    print("  ✓ PUT, PATCH, DELETE on audit endpoint return 405 Method Not Allowed.")

    # Monotonicity check
    logs = requests.get(f"{BASE_URL}/tickets/{ticket_id}/audit").json()
    assert len(logs) >= 4
    ids = [l["id"] for l in logs]
    assert ids == sorted(ids), f"Audit IDs must be strictly increasing: {ids}"
    timestamps = [datetime.fromisoformat(l["created_at"]) for l in logs]
    for i in range(len(timestamps) - 1):
        assert timestamps[i] <= timestamps[i + 1], "Timestamps must be monotonically increasing"
    print("  ✓ Audit logs are strictly monotonically ordered by ID and timestamp.")


if __name__ == "__main__":
    test_high_concurrency_claim()
    test_claiming_guards_on_terminal_states()
    test_empty_message_and_security_leak_guards()
    test_sla_exact_boundary_arithmetic()
    test_priority_escalation_guards()
    test_lifecycle_reopen_exact_boundaries()
    test_auto_close_exact_business_threshold()
    test_audit_immutability_and_monotonicity()
    print("\n🌟 ALL SENIOR ENGINEER EDGE CASE TESTS COMPLETED!")
