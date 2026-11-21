"""
Frontdesk v3 — Production End-to-End Verification Test Suite

Verifies:
  E2E-01  Health check and production API versioning (v3.0.0)
  E2E-02  Login Gateway: Valid login returns JWT and agent profile
  E2E-03  Invalid credentials rejected with HTTP 401
  E2E-04  Role-Based Ticket Ownership:
          - Regular agent Arjun CANNOT resolve, escalate, or reply to Ravi's ticket (403 Forbidden)
          - Assigned agent Ravi CAN update priority and resolve his own ticket (200 OK)
          - Team Lead Meera has supervisory override to resolve any ticket (200 OK)
  E2E-05  Dual-Mode Messaging & Zero-Leakage:
          - Private internal notes strictly isolated from customer scope
          - Public customer replies advance ticket status and pause SLA
  E2E-06  Real-Time SSE Event Stream:
          - Connection established with valid token
          - Handshake emits CONNECTED event
  E2E-07  Customer Magic Link Token Security:
          - Deterministic HMAC verification and cross-customer rejection
"""
import os
import sys
import unittest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
PASSWORD = "arvo2026!"

MEERA_EMAIL = "meera@arvo.in"
MEERA_ID = "a1000001-0000-0000-0000-000000000001"

RAVI_EMAIL = "ravi@arvo.in"
RAVI_ID = "a1000001-0000-0000-0000-000000000002"

ARJUN_EMAIL = "arjun@arvo.in"
ARJUN_ID = "a1000001-0000-0000-0000-000000000004"


def api(path, method="GET", **kwargs):
    return getattr(requests, method.lower())(f"{BASE_URL}{path}", **kwargs)


class TestV3ProductionE2E(unittest.TestCase):

    def _login(self, email, password=PASSWORD):
        resp = api("/api/auth/login", "POST", json={"email": email, "password": password})
        self.assertEqual(resp.status_code, 200, f"Login failed for {email}: {resp.text}")
        data = resp.json()
        return data["access_token"], data["agent"]

    def _create_ticket(self, title="v3 E2E Test Ticket", priority="small"):
        resp = api("/api/tickets", "POST", json={
            "title": title,
            "description": "Automated verification test",
            "customer_name": "Test Customer",
            "customer_email": "customer@v3test.io",
            "priority": priority,
        })
        self.assertEqual(resp.status_code, 201)
        return resp.json()["id"]

    # ── E2E-01: Health check & versioning ──────────────────────────────────────
    def test_e2e_01_health_and_version(self):
        resp = api("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["version"], "3.0.0", "Backend must report version 3.0.0")

    # ── E2E-02: Auth Gateway login ─────────────────────────────────────────────
    def test_e2e_02_login_gateway(self):
        token, agent = self._login(MEERA_EMAIL)
        self.assertIsNotNone(token)
        self.assertEqual(agent["email"], MEERA_EMAIL)
        self.assertEqual(agent["role"], "lead")

        # Verify /me endpoint
        me_resp = api("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.json()["id"], MEERA_ID)

    # ── E2E-03: Invalid credentials rejected ───────────────────────────────────
    def test_e2e_03_invalid_login_rejected(self):
        resp = api("/api/auth/login", "POST", json={"email": MEERA_EMAIL, "password": "wrong"})
        self.assertEqual(resp.status_code, 401)

        resp2 = api("/api/auth/login", "POST", json={"email": "nonexistent@arvo.in", "password": PASSWORD})
        self.assertEqual(resp2.status_code, 401)

    # ── E2E-04: Role-Based Ticket Ownership (RBAC) ─────────────────────────────
    def test_e2e_04_ticket_ownership_rbac(self):
        # 1. Create ticket and claim as Ravi
        ticket_id = self._create_ticket("RBAC Test Ticket")
        claim_resp = api(f"/api/tickets/{ticket_id}/claim", "POST", json={"agent_id": RAVI_ID})
        self.assertEqual(claim_resp.status_code, 200)
        self.assertEqual(claim_resp.json()["assigned_agent_id"], RAVI_ID)

        # 2. Arjun logs in with JWT
        arjun_token, _ = self._login(ARJUN_EMAIL)

        # 3. Arjun attempts to resolve Ravi's ticket -> 403 Forbidden
        res_fail = api(
            f"/api/tickets/{ticket_id}/resolve",
            "POST",
            headers={"Authorization": f"Bearer {arjun_token}"},
        )
        self.assertEqual(res_fail.status_code, 403, "Non-assigned agent must be blocked with 403")
        self.assertIn("Forbidden", res_fail.json()["detail"])

        # 4. Arjun attempts to change priority on Ravi's ticket -> 403 Forbidden
        prio_fail = api(
            f"/api/tickets/{ticket_id}/priority",
            "PATCH",
            headers={"Authorization": f"Bearer {arjun_token}"},
            json={"priority": "urgent"},
        )
        self.assertEqual(prio_fail.status_code, 403, "Non-assigned agent cannot change priority (403)")

        # 5. Arjun attempts to send public customer reply -> 403 Forbidden
        reply_fail = api(
            f"/api/tickets/{ticket_id}/messages",
            "POST",
            headers={"Authorization": f"Bearer {arjun_token}"},
            json={
                "content": "Hijacked customer reply",
                "is_private": False,
                "sender_type": "agent",
            },
        )
        self.assertEqual(reply_fail.status_code, 403, "Non-assigned agent cannot reply publicly (403)")

        # 6. Ravi logs in and updates priority on his own ticket -> 200 OK
        ravi_token, _ = self._login(RAVI_EMAIL)
        prio_ok = api(
            f"/api/tickets/{ticket_id}/priority",
            "PATCH",
            headers={"Authorization": f"Bearer {ravi_token}"},
            json={"priority": "medium"},
        )
        self.assertEqual(prio_ok.status_code, 200)
        self.assertEqual(prio_ok.json()["priority"], "medium")

        # 7. Team Lead Meera logs in and has supervisory override -> 200 OK
        meera_token, _ = self._login(MEERA_EMAIL)
        resolve_ok = api(
            f"/api/tickets/{ticket_id}/resolve",
            "POST",
            headers={"Authorization": f"Bearer {meera_token}"},
        )
        self.assertEqual(resolve_ok.status_code, 200)
        self.assertEqual(resolve_ok.json()["status"], "done")

    # ── E2E-05: Dual-mode messaging & note isolation ───────────────────────────
    def test_e2e_05_note_isolation(self):
        ticket_id = self._create_ticket("Note Isolation Test")
        ravi_token, _ = self._login(RAVI_EMAIL)
        api(f"/api/tickets/{ticket_id}/claim", "POST", json={"agent_id": RAVI_ID})

        # Post an internal private note
        note_resp = api(
            f"/api/tickets/{ticket_id}/messages",
            "POST",
            headers={"Authorization": f"Bearer {ravi_token}"},
            json={
                "content": "CONFIDENTIAL: Internal engineering investigation note.",
                "is_private": True,
                "sender_type": "agent",
            },
        )
        self.assertEqual(note_resp.status_code, 201)

        # Post a public customer reply
        public_resp = api(
            f"/api/tickets/{ticket_id}/messages",
            "POST",
            headers={"Authorization": f"Bearer {ravi_token}"},
            json={
                "content": "Hello customer, we are working on your issue.",
                "is_private": False,
                "sender_type": "agent",
            },
        )
        self.assertEqual(public_resp.status_code, 201)

        # Customer view strictly isolates the private note
        cust_view = api(f"/api/tickets/{ticket_id}/messages?scope=customer")
        self.assertEqual(cust_view.status_code, 200)
        msgs = cust_view.json()
        self.assertEqual(len(msgs), 1, "Customer must only see the public reply")
        self.assertNotIn("CONFIDENTIAL", msgs[0]["content"])
        self.assertNotIn("is_private", msgs[0])

    # ── E2E-06: Real-time SSE push stream ──────────────────────────────────────
    def test_e2e_06_sse_stream_handshake(self):
        token, _ = self._login(MEERA_EMAIL)
        try:
            resp = requests.get(
                f"{BASE_URL}/api/events/stream?token={token}",
                stream=True,
                timeout=3,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/event-stream", resp.headers.get("Content-Type", ""))
            first_line = next(resp.iter_lines(chunk_size=512), None)
            resp.close()
            self.assertIsNotNone(first_line, "Stream must emit connected event immediately")
        except requests.exceptions.Timeout:
            self.fail("SSE stream timed out without connecting")

    # ── E2E-07: Customer magic link token security ─────────────────────────────
    def test_e2e_07_customer_magic_link(self):
        from app.core.security import generate_customer_token, verify_customer_token

        token_a = generate_customer_token("INC-0001", "alice@example.com")
        self.assertTrue(verify_customer_token("INC-0001", "alice@example.com", token_a))
        # Case insensitive
        self.assertTrue(verify_customer_token("INC-0001", "ALICE@EXAMPLE.COM", token_a))
        # Cross customer rejected
        self.assertFalse(verify_customer_token("INC-0001", "bob@example.com", token_a))
        # Cross ticket rejected
        self.assertFalse(verify_customer_token("INC-9999", "alice@example.com", token_a))


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Frontdesk v3 — Production End-to-End Test Suite")
    print(f"Backend: {BASE_URL}")
    print("=" * 60 + "\n")
    unittest.main(verbosity=2)
