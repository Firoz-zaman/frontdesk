"""Automated Security & Data Leakage Prevention Test for Private Note Isolation (INC-0304).

Incident INC-0304: An agent wrote an internal note for the team that was mistakenly
sent to the customer. The requirement is:
'Private team notes must never be shown to a customer. Not on a screen.
Not in an API response. Not in an export. Not in a list.'
"""
import requests

BASE_URL = "http://localhost:8000/api"
AGENT_MEERA = "a1000001-0000-0000-0000-000000000001"


def create_test_ticket(title: str):
    res = requests.post(
        f"{BASE_URL}/tickets",
        json={
            "title": title,
            "description": "Testing private note isolation and data leakage wall",
            "customer_name": "Siddharth Sen",
            "customer_email": "siddharth@enterprise.com",
            "priority": "urgent",
        },
    )
    assert res.status_code == 201
    return res.json()


def test_customer_view_strictly_omits_private_notes():
    """Verify INC-0304: Customer query never returns private team notes."""
    ticket = create_test_ticket("INC-0304 Data Leakage Prevention")
    ticket_id = ticket["id"]
    print(f"\n[TEST 1] Testing with Ticket: {ticket_id}")

    # 1. Post a highly confidential internal note
    private_content = "CONFIDENTIAL: Customer threatens to cancel contract. Escalate to VP before offering credits."
    r1 = requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={
            "content": private_content,
            "is_private": True,
            "sender_type": "agent",
            "sender_id": AGENT_MEERA,
            "sender_name": "Meera",
        },
    )
    assert r1.status_code == 201
    assert r1.json()["is_private"] is True

    # 2. Post a public customer reply
    public_content = "Hello Siddharth, our senior team is looking into your account right now."
    r2 = requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={
            "content": public_content,
            "is_private": False,
            "sender_type": "agent",
            "sender_id": AGENT_MEERA,
            "sender_name": "Meera",
        },
    )
    assert r2.status_code == 201
    assert r2.json()["is_private"] is False

    # 3. Query Customer View (scope=customer)
    cust_res = requests.get(f"{BASE_URL}/tickets/{ticket_id}/messages?scope=customer")
    assert cust_res.status_code == 200
    cust_messages = cust_res.json()

    print(f"[TEST 1] Customer scope returned {len(cust_messages)} messages")
    assert len(cust_messages) == 1, f"Expected exactly 1 public message, got {len(cust_messages)}"
    assert cust_messages[0]["content"] == public_content
    # Ensure confidential content does not exist anywhere in the raw text response
    assert private_content not in cust_res.text
    # Ensure is_private flag is completely omitted from the customer schema
    assert "is_private" not in cust_messages[0]
    print("[TEST 1] PASS: Zero leakage in customer API response! Private note strictly omitted.")

    # 4. Query Agent View (scope=agent)
    agent_res = requests.get(f"{BASE_URL}/tickets/{ticket_id}/messages?scope=agent")
    assert agent_res.status_code == 200
    agent_messages = agent_res.json()

    print(f"[TEST 1] Agent scope returned {len(agent_messages)} messages")
    assert len(agent_messages) == 2
    private_msgs = [m for m in agent_messages if m["is_private"] is True]
    public_msgs = [m for m in agent_messages if m["is_private"] is False]
    assert len(private_msgs) == 1
    assert len(public_msgs) == 1
    assert private_msgs[0]["content"] == private_content
    print("[TEST 1] PASS: Agent correctly sees both internal notes and public replies.")


def test_customer_cannot_spoof_private_notes():
    """Verify customers cannot create private notes even if payload has is_private=True."""
    ticket = create_test_ticket("Customer Spoof Test")
    ticket_id = ticket["id"]

    r = requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={
            "content": "Customer message trying to be private",
            "is_private": True,
            "sender_type": "customer",
            "sender_name": "Siddharth",
        },
    )
    assert r.status_code == 201
    assert r.json()["is_private"] is False
    print("[TEST 2] PASS: Customer cannot force is_private=True (sanitized to False).")


def test_lifecycle_status_transitions_on_messages():
    """Verify ticket moves to 'waiting_on_customer' on public reply, and back to 'in_progress' on customer reply."""
    ticket = create_test_ticket("Status Transition Test")
    ticket_id = ticket["id"]

    # Claim ticket -> in_progress
    requests.post(f"{BASE_URL}/tickets/{ticket_id}/claim", json={"agent_id": AGENT_MEERA})
    t_after_claim = requests.get(f"{BASE_URL}/tickets/{ticket_id}").json()
    assert t_after_claim["status"] == "in_progress"

    # Agent writes private note -> status should remain 'in_progress'
    requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={"content": "Internal check", "is_private": True, "sender_type": "agent", "sender_id": AGENT_MEERA},
    )
    t_after_note = requests.get(f"{BASE_URL}/tickets/{ticket_id}").json()
    assert t_after_note["status"] == "in_progress"

    # Agent sends public reply -> status moves to 'waiting_on_customer'
    requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={"content": "Could you provide logs?", "is_private": False, "sender_type": "agent", "sender_id": AGENT_MEERA},
    )
    t_after_reply = requests.get(f"{BASE_URL}/tickets/{ticket_id}").json()
    assert t_after_reply["status"] == "waiting_on_customer"
    print("[TEST 3] PASS: Status moved to 'waiting_on_customer' after public agent reply.")

    # Customer replies back -> status moves back to 'in_progress'
    requests.post(
        f"{BASE_URL}/tickets/{ticket_id}/messages",
        json={"content": "Here are the logs attached.", "is_private": False, "sender_type": "customer"},
    )
    t_after_customer = requests.get(f"{BASE_URL}/tickets/{ticket_id}").json()
    assert t_after_customer["status"] == "in_progress"
    print("[TEST 3] PASS: Status returned to 'in_progress' when customer responded.")


if __name__ == "__main__":
    print("=== Running Note Isolation & Security Tests (INC-0304) ===")
    test_customer_view_strictly_omits_private_notes()
    test_customer_cannot_spoof_private_notes()
    test_lifecycle_status_transitions_on_messages()
    print("\nALL NOTE ISOLATION TESTS PASSED SUCCESSFULLY! (INC-0304 Solved)")
