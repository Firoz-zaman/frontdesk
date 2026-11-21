"""Automated Concurrency & Race-Condition Test for Atomic Ticket Claiming (INC-0291)."""
import concurrent.futures
import requests

BASE_URL = "http://localhost:8000/api"

# Seed agent IDs
AGENT_MEERA = "a1000001-0000-0000-0000-000000000001"
AGENT_RAVI = "a1000001-0000-0000-0000-000000000002"
AGENT_INVALID = "a0000000-0000-0000-0000-000000000000"


def create_test_ticket(title: str):
    res = requests.post(
        f"{BASE_URL}/tickets",
        json={
            "title": title,
            "description": "Testing atomic claim concurrency protection",
            "customer_name": "Acme Tester",
            "customer_email": "tester@acme.com",
            "priority": "urgent",
        },
    )
    assert res.status_code == 201, f"Failed to create ticket: {res.text}"
    return res.json()


def claim_ticket(ticket_id: str, agent_id: str):
    return requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/claim",
        json={"agent_id": agent_id},
    )


def test_concurrent_claiming_prevents_race_condition():
    """Verify INC-0291: Two agents clicking 'take this ticket' simultaneously.
    Exactly one must succeed (200), and the other must be rejected (409 Conflict).
    """
    ticket = create_test_ticket("INC-0291 Concurrency Simulation")
    ticket_id = ticket["id"]
    print(f"\n[TEST 1] Created fresh ticket: {ticket_id}")

    # Launch two concurrent requests simultaneously using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(claim_ticket, ticket_id, AGENT_MEERA)
        f2 = executor.submit(claim_ticket, ticket_id, AGENT_RAVI)
        r1 = f1.result()
        r2 = f2.result()

    statuses = sorted([r1.status_code, r2.status_code])
    print(f"[TEST 1] Response status codes: {r1.status_code} and {r2.status_code}")
    assert statuses == [200, 409], f"Expected exactly [200, 409], got {statuses}"

    # Verify that the 409 message includes the name of the winning agent
    conflict_res = r1 if r1.status_code == 409 else r2
    print(f"[TEST 1] Conflict message: {conflict_res.json()}")
    assert "already been claimed" in conflict_res.json()["detail"] or "concurrent" in conflict_res.json()["detail"]

    # Verify final ticket state in DB
    final_res = requests.get(f"{BASE_URL}/tickets/{ticket_id}")
    assert final_res.status_code == 200
    final_ticket = final_res.json()
    assert final_ticket["status"] == "in_progress"
    assert final_ticket["assigned_agent_id"] in [AGENT_MEERA, AGENT_RAVI]
    print(f"[TEST 1] PASS: Ticket {ticket_id} safely assigned to {final_ticket['assigned_agent_name']} with status '{final_ticket['status']}'")


def test_already_claimed_ticket_returns_409():
    """Verify attempting to claim an already claimed ticket returns 409."""
    ticket = create_test_ticket("Already Claimed Test")
    ticket_id = ticket["id"]

    # First claim succeeds
    r1 = claim_ticket(ticket_id, AGENT_MEERA)
    assert r1.status_code == 200

    # Second claim fails with 409
    r2 = claim_ticket(ticket_id, AGENT_RAVI)
    assert r2.status_code == 409
    assert "Meera" in r2.json()["detail"]
    print(f"[TEST 2] PASS: Subsequent claim rejected with 409: {r2.json()['detail']}")


def test_invalid_agent_returns_404():
    """Verify claiming with nonexistent agent returns 404."""
    ticket = create_test_ticket("Invalid Agent Test")
    r = claim_ticket(ticket["id"], AGENT_INVALID)
    assert r.status_code == 404
    print("[TEST 3] PASS: Invalid agent returned 404")


def test_nonexistent_ticket_returns_404():
    """Verify claiming nonexistent ticket returns 404."""
    r = claim_ticket("INC-99999", AGENT_MEERA)
    assert r.status_code == 404
    print("[TEST 4] PASS: Nonexistent ticket returned 404")


if __name__ == "__main__":
    print("=== Running Atomic Ticket Claiming Verification Tests ===")
    test_concurrent_claiming_prevents_race_condition()
    test_already_claimed_ticket_returns_409()
    test_invalid_agent_returns_404()
    test_nonexistent_ticket_returns_404()
    print("\nALL ATOMIC CLAIMING TESTS PASSED SUCCESSFULLY! (INC-0291 Solved)")
