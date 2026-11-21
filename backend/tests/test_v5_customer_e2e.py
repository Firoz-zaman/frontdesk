"""
Frontdesk v5 — Multi-Persona Customer Portal End-to-End Test Suite

Verifies:
  CUST-01  Customer Authentication: Valid login returns JWT and customer profile (Rahul Sharma).
  CUST-02  Invalid credentials properly rejected with HTTP 401.
  CUST-03  Customer Ticket Creation: Customer can create ticket; initial SLAs calculated.
  CUST-04  Cross-Customer Data Isolation: Customer A cannot access Customer B's tickets (403 Forbidden).
  CUST-05  Zero-Leakage Note Isolation Wall: Customer message query strictly excludes private notes.
  CUST-06  Full End-to-End SLA Cycle:
           - Agent posts public reply -> Status moves to waiting_on_customer (SLA timer paused).
           - Customer replies via Customer API -> Status resumes to in_progress (SLA clock unfreezes).
           - Audit event CUSTOMER_REPLY_RECEIVED logged.
  CUST-07  Role-Based Boundary: Customer credentials strictly blocked from agent endpoints (403 Forbidden).
"""
import os
import sys
import unittest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
PASSWORD = "arvo2026!"

AGENT_MEERA_EMAIL = "meera@arvo.in"
AGENT_MEERA_ID = "a1000001-0000-0000-0000-000000000001"

CUSTOMER_RAHUL_EMAIL = "customer@acmecorp.com"
CUSTOMER_NISHA_EMAIL = "nisha@globaltech.in"


class TestV5CustomerE2E(unittest.TestCase):
    """End-to-End verification of the Customer Portal and Agent-Customer interactions."""

    @classmethod
    def setUpClass(cls):
        # 1. Authenticate Team Lead Agent (Meera)
        res_agent = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": AGENT_MEERA_EMAIL,
            "password": PASSWORD,
        })
        assert res_agent.status_code == 200, f"Agent login failed: {res_agent.text}"
        cls.agent_token = res_agent.json()["access_token"]
        cls.agent_headers = {"Authorization": f"Bearer {cls.agent_token}"}

        # 2. Authenticate Customer (Rahul Sharma)
        res_cust = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CUSTOMER_RAHUL_EMAIL,
            "password": PASSWORD,
        })
        assert res_cust.status_code == 200, f"Customer login failed: {res_cust.text}"
        cls.customer_token = res_cust.json()["access_token"]
        cls.customer_headers = {"Authorization": f"Bearer {cls.customer_token}"}

    def test_cust_01_customer_auth_and_profile(self):
        """CUST-01: Customer login returns JWT, user_type='customer', and profile."""
        res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CUSTOMER_RAHUL_EMAIL,
            "password": PASSWORD,
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["user_type"], "customer")
        self.assertIsNotNone(data["customer"])
        self.assertEqual(data["customer"]["email"], CUSTOMER_RAHUL_EMAIL)
        self.assertEqual(data["customer"]["name"], "Rahul Sharma")
        self.assertEqual(data["customer"]["company"], "Acme Corporation")

        # Test /api/auth/me with customer token
        me_res = requests.get(f"{BASE_URL}/api/auth/me", headers=self.customer_headers)
        self.assertEqual(me_res.status_code, 200)
        me_data = me_res.json()
        self.assertEqual(me_data["user_type"], "customer")
        self.assertEqual(me_data["email"], CUSTOMER_RAHUL_EMAIL)

    def test_cust_02_invalid_credentials_rejected(self):
        """CUST-02: Bad customer password or non-existent email returns 401."""
        res1 = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": CUSTOMER_RAHUL_EMAIL,
            "password": "wrong_password_123",
        })
        self.assertEqual(res1.status_code, 401)

        res2 = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "nobody@nonexistent.invalid",
            "password": PASSWORD,
        })
        self.assertEqual(res2.status_code, 401)

    def test_cust_03_customer_ticket_creation_and_listing(self):
        """CUST-03: Customer can create ticket; initial SLAs and customer email are set."""
        create_res = requests.post(
            f"{BASE_URL}/api/customer/tickets",
            headers=self.customer_headers,
            json={
                "title": "Database connection pool exhaustion during peak load",
                "description": "Our backend is hitting max_connections limit intermittently.",
                "priority": "urgent",
            },
        )
        self.assertEqual(create_res.status_code, 201)
        ticket = create_res.json()
        ticket_id = ticket["id"]
        self.assertTrue(ticket_id.startswith("INC-"))
        self.assertEqual(ticket["customer_email"], CUSTOMER_RAHUL_EMAIL)
        self.assertEqual(ticket["status"], "open")
        self.assertIsNotNone(ticket["first_response_due_at"])
        self.assertIsNotNone(ticket["resolution_due_at"])

        # Customer lists tickets: newly created ticket must be present
        list_res = requests.get(f"{BASE_URL}/api/customer/tickets", headers=self.customer_headers)
        self.assertEqual(list_res.status_code, 200)
        my_ticket_ids = [t["id"] for t in list_res.json()]
        self.assertIn(ticket_id, my_ticket_ids)

    def test_cust_04_cross_customer_isolation(self):
        """CUST-04: Customer cannot view another customer's ticket (403 Forbidden)."""
        # INC-0002 belongs to Nisha Patel (GlobalTech Solutions)
        res = requests.get(f"{BASE_URL}/api/customer/tickets/INC-0002", headers=self.customer_headers)
        self.assertEqual(res.status_code, 403)
        self.assertIn("Forbidden", res.json().get("detail", ""))

    def test_cust_05_zero_leakage_note_isolation_wall(self):
        """CUST-05: Private agent notes are never exposed in customer message endpoints."""
        # 1. Customer creates a ticket
        c_res = requests.post(
            f"{BASE_URL}/api/customer/tickets",
            headers=self.customer_headers,
            json={
                "title": "Secret Note Isolation Test Ticket",
                "description": "Testing that internal notes do not leak.",
                "priority": "small",
            },
        )
        ticket_id = c_res.json()["id"]

        # 2. Agent posts a private internal note
        note_res = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/messages",
            headers=self.agent_headers,
            json={
                "content": "CONFIDENTIAL: Customer server has misconfigured firewall rules.",
                "is_private": True,
                "sender_type": "agent",
                "sender_id": AGENT_MEERA_ID,
                "sender_name": "Meera",
            },
        )
        self.assertIn(note_res.status_code, (200, 201))

        # 3. Agent posts a public response
        public_res = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/messages",
            headers=self.agent_headers,
            json={
                "content": "Hello Rahul, we are investigating your firewall settings.",
                "is_private": False,
                "sender_type": "agent",
                "sender_id": AGENT_MEERA_ID,
                "sender_name": "Meera",
            },
        )
        self.assertIn(public_res.status_code, (200, 201))

        # 4. Customer queries conversation: ONLY the public response must be returned!
        cust_msgs_res = requests.get(
            f"{BASE_URL}/api/customer/tickets/{ticket_id}/messages",
            headers=self.customer_headers,
        )
        self.assertEqual(cust_msgs_res.status_code, 200)
        messages = cust_msgs_res.json()
        contents = [m["content"] for m in messages]

        self.assertIn("Hello Rahul, we are investigating your firewall settings.", contents)
        self.assertNotIn("CONFIDENTIAL: Customer server has misconfigured firewall rules.", contents)

    def test_cust_06_end_to_end_sla_resumption_cycle(self):
        """CUST-06: Agent public reply pauses SLA; Customer reply unfreezes SLA and resumes in_progress."""
        # 1. Customer creates a ticket
        c_res = requests.post(
            f"{BASE_URL}/api/customer/tickets",
            headers=self.customer_headers,
            json={
                "title": "End-to-End SLA Resumption Cycle Ticket",
                "description": "Verifying status flips and clock pausing.",
                "priority": "medium",
            },
        )
        ticket_id = c_res.json()["id"]

        # 2. Agent claims ticket
        requests.post(f"{BASE_URL}/api/tickets/{ticket_id}/claim", headers=self.agent_headers, json={"agent_id": AGENT_MEERA_ID})

        # 3. Agent sends public reply -> moves ticket to waiting_on_customer
        reply_res = requests.post(
            f"{BASE_URL}/api/tickets/{ticket_id}/messages",
            headers=self.agent_headers,
            json={
                "content": "Could you please provide your server logs from /var/log/syslog?",
                "is_private": False,
                "sender_type": "agent",
                "sender_id": AGENT_MEERA_ID,
                "sender_name": "Meera",
            },
        )
        self.assertIn(reply_res.status_code, (200, 201))

        # Verify ticket status is waiting_on_customer and SLA is paused
        t_check1 = requests.get(f"{BASE_URL}/api/customer/tickets/{ticket_id}", headers=self.customer_headers).json()
        self.assertEqual(t_check1["status"], "waiting_on_customer")
        self.assertIsNotNone(t_check1["sla_paused_at"])

        # 4. Customer replies via Customer Portal
        cust_reply_res = requests.post(
            f"{BASE_URL}/api/customer/tickets/{ticket_id}/messages",
            headers=self.customer_headers,
            json={
                "content": "Uploaded syslog to the shared folder. Issue happened at 14:32 IST.",
            },
        )
        self.assertEqual(cust_reply_res.status_code, 201)

        # 5. Verify ticket automatically resumed to in_progress and sla_paused_at is cleared
        t_check2 = requests.get(f"{BASE_URL}/api/customer/tickets/{ticket_id}", headers=self.customer_headers).json()
        self.assertEqual(t_check2["status"], "in_progress")
        self.assertIsNone(t_check2["sla_paused_at"])

        # 6. Verify audit log recorded CUSTOMER_REPLY_RECEIVED
        audit_res = requests.get(f"{BASE_URL}/api/tickets/{ticket_id}/audit", headers=self.agent_headers)
        self.assertEqual(audit_res.status_code, 200)
        actions = [a["action"] for a in audit_res.json()]
        self.assertIn("CUSTOMER_REPLY_RECEIVED", actions)

    def test_cust_07_customer_credentials_blocked_from_agent_endpoints(self):
        """CUST-07: Customer token cannot access agent helpdesk endpoints (403 Forbidden)."""
        res = requests.post(
            f"{BASE_URL}/api/tickets/INC-0001/claim",
            headers=self.customer_headers,
            json={"agent_id": AGENT_MEERA_ID},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("Customer", res.json().get("detail", ""))

    def test_cust_08_customer_sse_stream_connection(self):
        """CUST-08: Customer JWT token connects to /api/events/stream and receives CONNECTED event."""
        s = requests.Session()
        res = s.get(
            f"{BASE_URL}/api/events/stream?token={self.customer_token}",
            stream=True,
            timeout=5,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/event-stream", res.headers.get("content-type", ""))
        
        # Read the first event
        event_type = None
        for line in res.iter_lines():
            if line:
                decoded = line.decode("utf-8")
                if decoded.startswith("event:"):
                    event_type = decoded.split("event:")[1].strip()
                    break
        self.assertEqual(event_type, "CONNECTED")
        res.close()


if __name__ == "__main__":
    unittest.main()
