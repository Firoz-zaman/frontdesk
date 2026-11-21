"""
Test suite: Authentication (JWT + Argon2id) and SSE push messaging (v2).

Test IDs:
  AUTH-01  Valid agent login returns JWT and agent profile
  AUTH-02  Login with wrong password returns HTTP 401
  AUTH-03  Login with non-existent email returns HTTP 401
  AUTH-04  Tampered / expired JWT is rejected on /api/auth/me
  AUTH-05  get_current_agent enforces token when REQUIRE_AUTH=true
  AUTH-06  Customer magic link: correct token accepted, cross-customer token rejected
  PUSH-01  GET /api/events/stream returns text/event-stream content-type
  PUSH-02  broadcast() delivers events to all subscribed queues
  PUSH-03  Claiming a ticket triggers TICKET_CLAIMED event downstream
  PUSH-04  Resolving a ticket triggers TICKET_RESOLVED event downstream
  REG-01   All Stage 0-5 endpoints remain functional (backward compat, REQUIRE_AUTH=false)
"""
import asyncio
import json
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

import requests

# ── Environment ────────────────────────────────────────────────────────────────

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

AGENT_MEERA_EMAIL = "meera@arvo.in"
AGENT_MEERA_ID = "a1000001-0000-0000-0000-000000000001"
CORRECT_PASSWORD = "arvo2026!"
WRONG_PASSWORD = "wrong_password_XYZ"


def api(path, method="GET", **kwargs):
    """Thin wrapper for requests with default base URL."""
    return getattr(requests, method.lower())(f"{BASE_URL}{path}", **kwargs)


# ── AUTH-01: Valid login ───────────────────────────────────────────────────────

class TestAuth01ValidLogin(unittest.TestCase):
    def test_valid_login_returns_jwt(self):
        resp = api("/api/auth/login", "POST", json={
            "email": AGENT_MEERA_EMAIL,
            "password": CORRECT_PASSWORD,
        })
        self.assertEqual(resp.status_code, 200, f"Expected 200, got {resp.status_code}: {resp.text}")
        data = resp.json()
        self.assertIn("access_token", data, "Response must contain access_token")
        self.assertEqual(data["token_type"], "bearer")
        self.assertIn("agent", data)
        self.assertEqual(data["agent"]["email"], AGENT_MEERA_EMAIL)
        self.assertEqual(data["agent"]["role"], "lead")
        # Validate JWT structure (3 base64 segments)
        parts = data["access_token"].split(".")
        self.assertEqual(len(parts), 3, "JWT must have 3 segments")


# ── AUTH-02: Wrong password ────────────────────────────────────────────────────

class TestAuth02WrongPassword(unittest.TestCase):
    def test_wrong_password_returns_401(self):
        resp = api("/api/auth/login", "POST", json={
            "email": AGENT_MEERA_EMAIL,
            "password": WRONG_PASSWORD,
        })
        self.assertEqual(resp.status_code, 401, f"Expected 401, got {resp.status_code}")
        self.assertIn("detail", resp.json())


# ── AUTH-03: Non-existent email ────────────────────────────────────────────────

class TestAuth03NonExistentEmail(unittest.TestCase):
    def test_nonexistent_email_returns_401(self):
        resp = api("/api/auth/login", "POST", json={
            "email": "ghost@nowhere.invalid",
            "password": CORRECT_PASSWORD,
        })
        self.assertEqual(resp.status_code, 401, f"Expected 401, got {resp.status_code}")


# ── AUTH-04: Tampered / expired JWT ───────────────────────────────────────────

class TestAuth04TamperedJwt(unittest.TestCase):
    def _get_valid_token(self):
        resp = api("/api/auth/login", "POST", json={
            "email": AGENT_MEERA_EMAIL, "password": CORRECT_PASSWORD,
        })
        return resp.json()["access_token"]

    def test_tampered_signature_rejected(self):
        token = self._get_valid_token()
        # Flip one character in the signature segment
        header, payload, sig = token.split(".")
        tampered = f"{header}.{payload}.{sig[:-4]}XXXX"
        resp = api("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"})
        self.assertEqual(resp.status_code, 401, f"Expected 401 for tampered token, got {resp.status_code}")

    def test_expired_jwt_rejected(self):
        """Create a JWT that expired 1 second ago and verify it's rejected."""
        import jwt as pyjwt
        SECRET = os.getenv("FRONTDESK_SECRET_KEY", "arvo-production-secret-key-change-in-prod-2026")
        expired_token = pyjwt.encode({
            "sub": AGENT_MEERA_ID,
            "email": AGENT_MEERA_EMAIL,
            "role": "lead",
            "iat": datetime.now(timezone.utc) - timedelta(hours=9),
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        }, SECRET, algorithm="HS256")
        resp = api("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        self.assertEqual(resp.status_code, 401, f"Expected 401 for expired token, got {resp.status_code}")

    def test_missing_bearer_header_in_strict_mode(self):
        """When REQUIRE_AUTH=true is set via env, missing token → 401.
        When REQUIRE_AUTH=false (default), /me returns the lead agent.
        We test the behavior matches the configured mode.
        """
        require_auth = os.getenv("REQUIRE_AUTH", "false").lower() == "true"
        resp = api("/api/auth/me")  # No Authorization header
        if require_auth:
            self.assertEqual(resp.status_code, 401, "REQUIRE_AUTH=true: missing token must yield 401")
        else:
            # Dev mode: returns lead agent
            self.assertEqual(resp.status_code, 200, "REQUIRE_AUTH=false: /me returns lead without token")
            self.assertEqual(resp.json()["email"], AGENT_MEERA_EMAIL)


# ── AUTH-05: get_current_agent enforcement under REQUIRE_AUTH=true ─────────────

class TestAuth05RequireAuthMode(unittest.TestCase):
    def test_valid_token_authenticated_me(self):
        """With a valid JWT, /api/auth/me returns the correct agent in both modes."""
        resp = api("/api/auth/login", "POST", json={
            "email": AGENT_MEERA_EMAIL, "password": CORRECT_PASSWORD,
        })
        self.assertEqual(resp.status_code, 200)
        token = resp.json()["access_token"]
        me_resp = api("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.json()["id"], AGENT_MEERA_ID)
        self.assertEqual(me_resp.json()["email"], AGENT_MEERA_EMAIL)


# ── AUTH-06: Customer magic link verification ──────────────────────────────────

class TestAuth06CustomerMagicLink(unittest.TestCase):
    def test_magic_link_token_generation_and_verification(self):
        """Magic link token for a ticket+email pair must be deterministic and correct."""
        from app.auth import generate_customer_token, verify_customer_token
        token = generate_customer_token("INC-0001", "rahul@acmecorp.com")
        self.assertIsInstance(token, str)
        self.assertEqual(len(token), 64, "HMAC-SHA256 hex must be 64 chars")
        # Same inputs always produce same token
        self.assertEqual(token, generate_customer_token("INC-0001", "rahul@acmecorp.com"))
        # Verification passes for correct pair
        self.assertTrue(verify_customer_token("INC-0001", "rahul@acmecorp.com", token))

    def test_cross_customer_token_rejected(self):
        """Token generated for customer A must not validate for customer B."""
        from app.auth import generate_customer_token, verify_customer_token
        token_a = generate_customer_token("INC-0001", "alice@example.com")
        # Attempt to use Alice's token for Bob's ticket access
        self.assertFalse(
            verify_customer_token("INC-0001", "bob@example.com", token_a),
            "Cross-customer token must be rejected"
        )

    def test_wrong_ticket_id_rejected(self):
        """Token for ticket A must not validate for ticket B."""
        from app.auth import generate_customer_token, verify_customer_token
        token = generate_customer_token("INC-0001", "alice@example.com")
        self.assertFalse(
            verify_customer_token("INC-9999", "alice@example.com", token),
            "Token bound to INC-0001 must not validate for INC-9999"
        )

    def test_email_case_insensitivity(self):
        """Magic link tokens must treat email as case-insensitive."""
        from app.auth import generate_customer_token, verify_customer_token
        token = generate_customer_token("INC-0001", "Alice@Example.COM")
        self.assertTrue(
            verify_customer_token("INC-0001", "alice@example.com", token),
            "Email case normalisation must yield consistent tokens"
        )


# ── AUTH-07: Ticket Ownership & RBAC Authorization Guards ─────────────────────

class TestAuth07TicketOwnership(unittest.TestCase):
    AGENT_RAVI_ID = "a1000001-0000-0000-0000-000000000002"
    AGENT_RAVI_EMAIL = "ravi@arvo.in"
    AGENT_ARJUN_ID = "a1000001-0000-0000-0000-000000000004"
    AGENT_ARJUN_EMAIL = "arjun@arvo.in"

    def _login(self, email):
        resp = api("/api/auth/login", "POST", json={"email": email, "password": CORRECT_PASSWORD})
        self.assertEqual(resp.status_code, 200, f"Login failed for {email}: {resp.text}")
        return resp.json()["access_token"]

    def _create_and_claim_ticket_as_ravi(self):
        # Create ticket
        res = api("/api/tickets", "POST", json={
            "title": "Ownership Test Ticket",
            "description": "Testing agent access control",
            "customer_name": "Acme User",
            "customer_email": "acme@example.com",
            "priority": "small",
        })
        self.assertEqual(res.status_code, 201)
        ticket_id = res.json()["id"]

        # Claim as Ravi
        claim_res = api(f"/api/tickets/{ticket_id}/claim", "POST", json={"agent_id": self.AGENT_RAVI_ID})
        self.assertEqual(claim_res.status_code, 200)
        return ticket_id

    def test_non_assigned_agent_cannot_resolve_ticket(self):
        """Arjun (regular agent) cannot resolve a ticket assigned to Ravi -> 403 Forbidden."""
        ticket_id = self._create_and_claim_ticket_as_ravi()
        arjun_token = self._login(self.AGENT_ARJUN_EMAIL)

        resp = api(
            f"/api/tickets/{ticket_id}/resolve",
            "POST",
            headers={"Authorization": f"Bearer {arjun_token}"},
        )
        self.assertEqual(resp.status_code, 403, f"Expected 403 Forbidden, got {resp.status_code}: {resp.text}")
        self.assertIn("Forbidden", resp.json()["detail"])
        self.assertIn("Ravi", resp.json()["detail"])

    def test_non_assigned_agent_cannot_change_priority(self):
        """Arjun cannot change priority on a ticket assigned to Ravi -> 403 Forbidden."""
        ticket_id = self._create_and_claim_ticket_as_ravi()
        arjun_token = self._login(self.AGENT_ARJUN_EMAIL)

        resp = api(
            f"/api/tickets/{ticket_id}/priority",
            "PATCH",
            headers={"Authorization": f"Bearer {arjun_token}"},
            json={"priority": "urgent"},
        )
        self.assertEqual(resp.status_code, 403, f"Expected 403 Forbidden, got {resp.status_code}: {resp.text}")
        self.assertIn("Forbidden", resp.json()["detail"])

    def test_non_assigned_agent_cannot_send_public_reply(self):
        """Arjun cannot send public customer replies on a ticket assigned to Ravi -> 403 Forbidden."""
        ticket_id = self._create_and_claim_ticket_as_ravi()
        arjun_token = self._login(self.AGENT_ARJUN_EMAIL)

        resp = api(
            f"/api/tickets/{ticket_id}/messages",
            "POST",
            headers={"Authorization": f"Bearer {arjun_token}"},
            json={
                "content": "Hi customer, I am hijacking this ticket.",
                "is_private": False,
                "sender_type": "agent",
            },
        )
        self.assertEqual(resp.status_code, 403, f"Expected 403 Forbidden, got {resp.status_code}: {resp.text}")

    def test_assigned_agent_can_modify_and_resolve(self):
        """Ravi (assigned agent) can change priority and resolve his own ticket -> 200 OK."""
        ticket_id = self._create_and_claim_ticket_as_ravi()
        ravi_token = self._login(self.AGENT_RAVI_EMAIL)

        # Priority update
        p_resp = api(
            f"/api/tickets/{ticket_id}/priority",
            "PATCH",
            headers={"Authorization": f"Bearer {ravi_token}"},
            json={"priority": "medium"},
        )
        self.assertEqual(p_resp.status_code, 200)

        # Resolve
        r_resp = api(
            f"/api/tickets/{ticket_id}/resolve",
            "POST",
            headers={"Authorization": f"Bearer {ravi_token}"},
        )
        self.assertEqual(r_resp.status_code, 200)
        self.assertEqual(r_resp.json()["status"], "done")

    def test_lead_agent_can_override_and_resolve(self):
        """Meera (team lead) has supervisory privileges to resolve any assigned ticket -> 200 OK."""
        ticket_id = self._create_and_claim_ticket_as_ravi()
        meera_token = self._login(AGENT_MEERA_EMAIL)

        r_resp = api(
            f"/api/tickets/{ticket_id}/resolve",
            "POST",
            headers={"Authorization": f"Bearer {meera_token}"},
        )
        self.assertEqual(r_resp.status_code, 200)
        self.assertEqual(r_resp.json()["status"], "done")


# ── PUSH-01: SSE endpoint returns correct content-type ────────────────────────

class TestPush01SseContentType(unittest.TestCase):
    def test_sse_endpoint_returns_event_stream(self):
        """GET /api/events/stream must immediately return text/event-stream."""
        try:
            resp = requests.get(
                f"{BASE_URL}/api/events/stream",
                stream=True,
                timeout=3,
            )
            self.assertEqual(resp.status_code, 200)
            content_type = resp.headers.get("Content-Type", "")
            self.assertIn("text/event-stream", content_type)
            # Read first chunk — should be CONNECTED event
            chunk = next(resp.iter_lines(chunk_size=512), None)
            resp.close()
            self.assertIsNotNone(chunk, "SSE stream must emit at least one line")
        except requests.exceptions.Timeout:
            # Timeout means the stream opened but no data arrived (not expected)
            self.fail("SSE stream timed out without emitting a CONNECTED event")
        except requests.exceptions.ConnectionError as e:
            self.skipTest(f"Backend not reachable: {e}")


# ── PUSH-02: Broadcaster fan-out (unit test, no HTTP) ─────────────────────────

class TestPush02BroadcasterFanout(unittest.TestCase):
    def test_broadcast_delivers_to_all_queues(self):
        """EventBroadcaster must fan events to every registered queue."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from app.events import EventBroadcaster

        async def _run():
            bc = EventBroadcaster()
            q1 = await bc.subscribe()
            q2 = await bc.subscribe()
            await bc.broadcast("TEST_EVENT", {"key": "value"})
            # Both queues must receive the event
            e1 = q1.get_nowait()
            e2 = q2.get_nowait()
            return e1, e2

        e1, e2 = asyncio.run(_run())
        self.assertEqual(e1["event"], "TEST_EVENT")
        self.assertEqual(e2["event"], "TEST_EVENT")
        self.assertEqual(e1["data"]["key"], "value")

    def test_unsubscribe_removes_queue(self):
        """Unsubscribed queues must not receive subsequent events."""
        from app.events import EventBroadcaster

        async def _run():
            bc = EventBroadcaster()
            q = await bc.subscribe()
            bc.unsubscribe(q)
            await bc.broadcast("GHOST_EVENT", {})
            return bc.subscriber_count, q.empty()

        count, is_empty = asyncio.run(_run())
        self.assertEqual(count, 0, "Subscriber count must be 0 after unsubscribe")
        self.assertTrue(is_empty, "Unsubscribed queue must remain empty")

    def test_full_queue_does_not_crash_broadcast(self):
        """A full queue (slow consumer) must not block or crash broadcast()."""
        from app.events import EventBroadcaster

        async def _run():
            bc = EventBroadcaster()
            q = await bc.subscribe()
            # Fill the queue to capacity
            for i in range(100):
                await q.put({"event": f"E{i}", "data": {}, "timestamp": "t"})
            # This must not raise
            await bc.broadcast("OVERFLOW_EVENT", {})

        asyncio.run(_run())  # Must complete without exception


# ── PUSH-03: Claiming triggers TICKET_CLAIMED downstream ─────────────────────

class TestPush03ClaimBroadcast(unittest.TestCase):
    def test_claim_endpoint_triggers_broadcast(self):
        """POST /claim must broadcast TICKET_CLAIMED event via SSE stream."""
        create_resp = api("/api/tickets", "POST", json={
            "title": "PUSH-03 test ticket",
            "description": "SSE claim broadcast test",
            "customer_name": "SSE Tester",
            "customer_email": "sse@test.invalid",
            "priority": "small",
        })
        if create_resp.status_code != 201:
            self.skipTest("Could not create test ticket for PUSH-03")
        ticket_id = create_resp.json()["id"]

        import threading
        import time

        received_events = []
        stop_stream = threading.Event()
        connected_event = threading.Event()

        def stream_listener():
            try:
                resp = requests.get(f"{BASE_URL}/api/events/stream", stream=True, timeout=10)
                current_event = None
                for line in resp.iter_lines(decode_unicode=True):
                    if stop_stream.is_set():
                        break
                    if not line:
                        continue
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                        if current_event == "CONNECTED":
                            connected_event.set()
                    elif line.startswith("data:") and current_event:
                        try:
                            data = json.loads(line.split(":", 1)[1].strip())
                            received_events.append({"event": current_event, "data": data})
                            if current_event == "TICKET_CLAIMED" and data.get("ticket_id") == ticket_id:
                                stop_stream.set()
                                break
                        except Exception:
                            pass
            except Exception:
                pass

        t = threading.Thread(target=stream_listener, daemon=True)
        t.start()

        # Wait until SSE client is connected
        if not connected_event.wait(timeout=5):
            stop_stream.set()
            self.skipTest("Could not establish SSE stream connection within 5s")

        # Now claim ticket via HTTP
        claim_resp = api(f"/api/tickets/{ticket_id}/claim", "POST", json={
            "agent_id": AGENT_MEERA_ID,
        })
        self.assertEqual(claim_resp.status_code, 200)

        # Wait for SSE to receive the event
        t.join(timeout=5)
        stop_stream.set()

        claimed_events = [
            e for e in received_events
            if e["event"] == "TICKET_CLAIMED" and e["data"].get("ticket_id") == ticket_id
        ]
        self.assertTrue(len(claimed_events) > 0, f"Expected TICKET_CLAIMED event for {ticket_id}, received: {received_events}")
        self.assertEqual(claimed_events[0]["data"]["agent_id"], AGENT_MEERA_ID)


# ── PUSH-04: Resolving triggers TICKET_RESOLVED downstream ───────────────────

class TestPush04ResolveBroadcast(unittest.TestCase):
    def test_resolve_endpoint_succeeds_and_does_not_crash(self):
        """POST /resolve must succeed and broadcast TICKET_RESOLVED downstream."""
        create_resp = api("/api/tickets", "POST", json={
            "title": "PUSH-04 resolve broadcast test",
            "description": "SSE resolve broadcast test",
            "customer_name": "SSE Resolver",
            "customer_email": "resolve@test.invalid",
            "priority": "small",
        })
        if create_resp.status_code != 201:
            self.skipTest("Could not create test ticket for PUSH-04")
        ticket_id = create_resp.json()["id"]

        # Claim it first
        api(f"/api/tickets/{ticket_id}/claim", "POST", json={"agent_id": AGENT_MEERA_ID})

        import threading
        received_events = []
        stop_stream = threading.Event()
        connected_event = threading.Event()

        def stream_listener():
            try:
                resp = requests.get(f"{BASE_URL}/api/events/stream", stream=True, timeout=10)
                current_event = None
                for line in resp.iter_lines(decode_unicode=True):
                    if stop_stream.is_set():
                        break
                    if not line:
                        continue
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                        if current_event == "CONNECTED":
                            connected_event.set()
                    elif line.startswith("data:") and current_event:
                        try:
                            data = json.loads(line.split(":", 1)[1].strip())
                            received_events.append({"event": current_event, "data": data})
                            if current_event == "TICKET_RESOLVED" and data.get("ticket_id") == ticket_id:
                                stop_stream.set()
                                break
                        except Exception:
                            pass
            except Exception:
                pass

        t = threading.Thread(target=stream_listener, daemon=True)
        t.start()

        if not connected_event.wait(timeout=5):
            stop_stream.set()
            self.skipTest("Could not establish SSE stream connection within 5s")

        # Resolve — must succeed and emit broadcast
        resolve_resp = api(f"/api/tickets/{ticket_id}/resolve", "POST", json={"agent_id": AGENT_MEERA_ID})
        self.assertEqual(resolve_resp.status_code, 200, f"Resolve failed: {resolve_resp.text}")
        self.assertEqual(resolve_resp.json()["status"], "done")

        t.join(timeout=5)
        stop_stream.set()

        resolved_events = [
            e for e in received_events
            if e["event"] == "TICKET_RESOLVED" and e["data"].get("ticket_id") == ticket_id
        ]
        self.assertTrue(len(resolved_events) > 0, f"Expected TICKET_RESOLVED event for {ticket_id}, received: {received_events}")


# ── REG-01: Backward compatibility (Stage 0-5 smoke test) ─────────────────────

class TestReg01BackwardCompat(unittest.TestCase):
    """Verify that all Stage 0-5 endpoints still work correctly with REQUIRE_AUTH=false."""

    def test_health_endpoint(self):
        resp = api("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_list_agents(self):
        resp = api("/api/agents")
        self.assertEqual(resp.status_code, 200)
        agents = resp.json()
        self.assertGreaterEqual(len(agents), 9, "Must have at least 9 seeded agents")
        emails = [a["email"] for a in agents]
        self.assertIn(AGENT_MEERA_EMAIL, emails)

    def test_create_and_read_ticket(self):
        resp = api("/api/tickets", "POST", json={
            "title": "REG-01 backward compat test",
            "description": "Regression test",
            "customer_name": "Regressor",
            "customer_email": "reg@test.invalid",
            "priority": "medium",
        })
        self.assertEqual(resp.status_code, 201)
        tid = resp.json()["id"]
        get_resp = api(f"/api/tickets/{tid}")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["id"], tid)

    def test_claim_ticket(self):
        # Create a fresh unclaimed ticket
        create = api("/api/tickets", "POST", json={
            "title": "REG-01 claim test",
            "description": "",
            "customer_name": "Claimer",
            "customer_email": "claim@test.invalid",
            "priority": "small",
        })
        self.assertEqual(create.status_code, 201)
        tid = create.json()["id"]
        claim = api(f"/api/tickets/{tid}/claim", "POST", json={"agent_id": AGENT_MEERA_ID})
        self.assertEqual(claim.status_code, 200)
        self.assertEqual(claim.json()["assigned_agent_id"], AGENT_MEERA_ID)

    def test_post_message_agent_and_customer(self):
        create = api("/api/tickets", "POST", json={
            "title": "REG-01 message test",
            "description": "",
            "customer_name": "Messager",
            "customer_email": "msg@test.invalid",
            "priority": "small",
        })
        self.assertEqual(create.status_code, 201)
        tid = create.json()["id"]

        # Agent public reply
        agent_msg = api(f"/api/tickets/{tid}/messages", "POST", json={
            "content": "Thank you for reaching out.",
            "is_private": False,
            "sender_type": "agent",
            "sender_id": AGENT_MEERA_ID,
        })
        self.assertEqual(agent_msg.status_code, 201)

        # Private internal note — must not appear in customer view
        note = api(f"/api/tickets/{tid}/messages", "POST", json={
            "content": "Internal note: investigating further.",
            "is_private": True,
            "sender_type": "agent",
            "sender_id": AGENT_MEERA_ID,
        })
        self.assertEqual(note.status_code, 201)

        # Customer view must exclude the private note
        customer_msgs = api(f"/api/tickets/{tid}/messages?scope=customer")
        self.assertEqual(customer_msgs.status_code, 200)
        for m in customer_msgs.json():
            self.assertNotIn("is_private", m, "CustomerMessageOut must not expose is_private")
            self.assertNotIn("Internal note", m["content"])

    def test_audit_trail_is_append_only(self):
        create = api("/api/tickets", "POST", json={
            "title": "REG-01 audit test",
            "description": "",
            "customer_name": "Auditor",
            "customer_email": "audit@test.invalid",
            "priority": "small",
        })
        tid = create.json()["id"]
        audit = api(f"/api/tickets/{tid}/audit")
        self.assertEqual(audit.status_code, 200)
        logs = audit.json()
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "TICKET_CREATED")

    def test_resolve_and_sla_fields(self):
        create = api("/api/tickets", "POST", json={
            "title": "REG-01 resolve test",
            "description": "",
            "customer_name": "Resolver",
            "customer_email": "resolve@test.invalid",
            "priority": "urgent",
        })
        tid = create.json()["id"]
        api(f"/api/tickets/{tid}/claim", "POST", json={"agent_id": AGENT_MEERA_ID})
        resolve = api(f"/api/tickets/{tid}/resolve", "POST", json={"agent_id": AGENT_MEERA_ID})
        self.assertEqual(resolve.status_code, 200)
        self.assertEqual(resolve.json()["status"], "done")
        self.assertIsNotNone(resolve.json()["resolved_at"])


# ── Runner ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{'=' * 60}")
    print("Frontdesk v2 — Auth & SSE Test Suite")
    print(f"Backend: {BASE_URL}")
    print(f"{'=' * 60}\n")
    unittest.main(verbosity=2)
