# Project Context & Implementation Record

> **System**: Frontdesk Support Portal  
> **Company**: Arvo Systems (iNav Technologies)  
> **Documentation Standard**: Strict adherence to hiring specification and modular implementation guidelines.

---

## 1. Context & Background

Arvo Systems operates with nine support agents handling approximately 40 customer tickets daily. The previous shared spreadsheet and WhatsApp workflow broke down due to lack of concurrency control, data leakage, and untracked response times.

---

## 2. Step 1: Pluggable Module 1 — Atomic Ticket Claiming (`INC-0291`)

### Incident INC-0291 (14 October) — Problem Addressed
* **Incident Summary**: Two support agents simultaneously opened the same customer ticket, clicked "take this ticket", and replied within one minute of each other with conflicting advice.
* **Root Cause**: The shared spreadsheet allowed simultaneous modifications with no mutual exclusion or atomic locking.
* **Objective for Step 1**: Build a pluggable, race-condition-proof atomic claiming mechanism so only one agent can claim a ticket. If another agent attempts to claim it concurrently, the system immediately rejects the second request with `HTTP 409 Conflict` and displays the winning assignee.

### Implementation Pieces:
1. **Backend DTO & Concurrency Endpoint** (`backend/app/schemas.py`, `backend/app/main.py`):
   - `ClaimRequest` Pydantic model (`agent_id: str`).
   - Atomic conditional update:
     ```python
     result = db.execute(
         update(Ticket)
         .where(Ticket.id == ticket_id, Ticket.assigned_agent_id.is_(None))
         .values(assigned_agent_id=payload.agent_id, status="in_progress")
     )
     ```
   - If `result.rowcount == 0`, rolls back and returns `HTTP 409 Conflict` with the winning agent's name.
2. **Frontend UI & Real-Time Conflict Handling** (`frontend/src/api.js`, `frontend/src/App.jsx`, `frontend/src/index.css`):
   - Claim action banner: `[ ✋ Take this ticket as {CurrentAgent} ]`.
   - On 409 Conflict: Informative alert and immediate state re-sync.
3. **Automated Concurrency Test Suite** (`backend/tests/test_atomic_claim.py`):
   - Concurrent worker threads verified that status codes are strictly `[200, 409]`. All 4 tests passed.

---

## 3. Step 2: Pluggable Module 2 — Dual-Mode Messaging & Note Isolation (`INC-0304`)

### Incident INC-0304 (22 October) — Problem Addressed
* **Incident Summary**: An agent wrote a private internal note explaining how to handle a difficult customer. By mistake, the note was sent to that customer. Arvo almost lost the customer.
* **Exact Specification Requirement**:
  > *"Private team notes must never be shown to a customer. Not on a screen. Not in an API response. Not in an export. Not in a list."*
* **Objective for Step 2**: Implement a zero-leakage dual-mode messaging system where private internal notes and public replies have strict separation at the database, query, serialization, and UI layers.

### Implementation Pieces:
1. **Database Model & DTO Data Isolation Barrier** (`backend/app/models.py`, `backend/app/schemas.py`):
   - Table `messages`: `id`, `ticket_id`, `sender_type`, `sender_id`, `sender_name`, `content`, `is_private`, `created_at`.
   - DTOs: `MessageOut` for internal agent queries, `CustomerMessageOut` which unconditionally omits `is_private` and internal agent metadata.
2. **API Endpoints with Database-Level Filtering** (`backend/app/main.py`):
   - `GET /api/tickets/{ticket_id}/messages`: When `scope="customer"`, filters `Message.is_private == False` at query level.
   - `POST /api/tickets/{ticket_id}/messages`: Forces `is_private=False` for customer senders, transitions status to `waiting_on_customer` on public agent reply, and back to `in_progress` on customer reply.
3. **Frontend Dual-Mode Timeline & Composer** (`frontend/src/App.jsx`, `frontend/src/index.css`):
   - Distinct visual styles: Slate/blue for public replies, high-contrast amber for private team notes with lock badge.
   - Composer mode switch between `💬 Reply to Customer` and `🔒 Private Team Note (Internal)` with security warning banners.
4. **Automated Verification Test Suite** (`backend/tests/test_note_isolation.py`):
   - Proved zero-leakage guarantee in customer responses and verified status lifecycle transitions.

---

## 4. Step 3: Pluggable Module 3 — Immutable Audit Event Sourcing (`INC-0318`)

### Incident INC-0318 (04 November) — Problem Addressed
* **Incident Summary**: A customer claimed Arvo did not reply until the next morning. Arvo believed the reply was sent in forty minutes. Nobody could prove who was right.
* **Exact Specification Requirement**:
  > *"The system must record exactly what happened, when it happened, and who did it. Nobody should be able to change that record later."*
* **Objective for Step 3**: Build an immutable, append-only event sourcing audit system that automatically logs every state change and interaction with tamper-proof timestamps and actor identities.

### Implementation Pieces:

#### Piece 1: Database Model & Decoupled Audit Service Layer
* **Data Model** (`backend/app/models.py`):
  - Table `audit_logs`:
    - `id`: INTEGER (Primary Key, Auto-increment)
    - `ticket_id`: Foreign Key (`tickets.id`)
    - `actor_type`: VARCHAR(20) (`agent` | `customer` | `system`)
    - `actor_id`: VARCHAR(100) (nullable)
    - `actor_name`: VARCHAR(100)
    - `action`: VARCHAR(50) (`TICKET_CREATED`, `TICKET_CLAIMED`, `PUBLIC_REPLY_SENT`, `INTERNAL_NOTE_ADDED`, `CUSTOMER_REPLY_RECEIVED`)
    - `details`: JSON (Context delta payload)
    - `created_at`: TIMESTAMP WITH TIME ZONE (UTC, default `now()`)
* **Decoupled Audit Service** (`backend/app/audit.py`):
  - Function: `log_audit(db, ticket_id, actor_type, actor_name, action, details, actor_id)`
  - Designed for high resilience: errors in audit logging are caught and logged so primary ticket operations are never blocked.

#### Piece 2: Event Hooks & Read-Only Audit Endpoint
* **Lifecycle Hooks** (`backend/app/main.py`):
  - `POST /api/tickets`: Emits `TICKET_CREATED` with customer name and ticket parameters.
  - `POST /api/tickets/{id}/claim`: Emits `TICKET_CLAIMED` with winning agent name.
  - `POST /api/tickets/{id}/messages`:
    - If `is_private == True`: Emits `INTERNAL_NOTE_ADDED` with agent name.
    - If `is_private == False` (Agent): Emits `PUBLIC_REPLY_SENT` with status update to `waiting_on_customer`.
    - If `sender_type == "customer"`: Emits `CUSTOMER_REPLY_RECEIVED`.
* **Read-Only Audit Endpoint** (`backend/app/main.py`):
  - `GET /api/tickets/{id}/audit`: Returns chronological list of audit records.
  - **Immutability Guarantee**: Strictly read-only; no `PUT`, `PATCH`, `DELETE`, or `POST` modification endpoints exist on audit logs.

#### Piece 3: Frontend Audit Trail Tab in Ticket Workspace
* **Client API** (`frontend/src/api.js`):
  - Added `fetchAuditLogs(ticketId)`.
* **Workspace View Tabs** (`frontend/src/App.jsx`, `frontend/src/index.css`):
  - Tab Switcher:
    - Tab 1: `💬 Conversation & Notes ({count})`
    - Tab 2: `📋 Audit Trail ({count})`
  - **Audit History View**:
    - Header banner emphasizing tamper-proof append-only nature (`INC-0318`).
    - Chronological list of events with formatted timestamp (including seconds and date).
    - Actor badge with role tag (`AGENT`, `CUSTOMER`, `SYSTEM`).
    - Action type badge with color-coding (`TICKET_CREATED`, `TICKET_CLAIMED`, `PUBLIC_REPLY_SENT`, `INTERNAL_NOTE_ADDED`, etc.).
    - Expandable details box showing state delta and preview.

#### Piece 4: Automated Verification Test Suite
* **Test Suite** (`backend/tests/test_audit_trail.py`):
  - `test_audit_trail_records_full_lifecycle`: Verified all 5 lifecycle events are recorded in exact order.
  - `test_dispute_resolution_non_repudiation`: Conclusively resolves INC-0318 by calculating mathematical response intervals between creation and agent reply.
  - `test_audit_logs_are_read_only_and_immutable`: Verified attempts to POST, PUT, or DELETE audit logs return `405 Method Not Allowed`.

---

## 5. Comprehensive Verification Test Suite Results (Steps 1, 2, and 3)

```
=== Running Atomic Ticket Claiming Verification Tests ===
[TEST 1] Created fresh ticket: INC-0020
[TEST 1] Response status codes: 200 and 409
[TEST 1] Conflict message: {'detail': 'Ticket has already been claimed by Meera.'}
[TEST 1] PASS: Ticket INC-0020 safely assigned to Meera with status 'in_progress'
[TEST 2] PASS: Subsequent claim rejected with 409: Ticket has already been claimed by Meera.
[TEST 3] PASS: Invalid agent returned 404
[TEST 4] PASS: Nonexistent ticket returned 404
ALL ATOMIC CLAIMING TESTS PASSED SUCCESSFULLY! (INC-0291 Solved)

=== Running Note Isolation & Security Tests (INC-0304) ===
[TEST 1] Testing with Ticket: INC-0023
[TEST 1] Customer scope returned 1 messages
[TEST 1] PASS: Zero leakage in customer API response! Private note strictly omitted.
[TEST 1] Agent scope returned 2 messages
[TEST 1] PASS: Agent correctly sees both internal notes and public replies.
[TEST 2] PASS: Customer cannot force is_private=True (sanitized to False).
[TEST 3] PASS: Status moved to 'waiting_on_customer' after public agent reply.
[TEST 3] PASS: Status returned to 'in_progress' when customer responded.
ALL NOTE ISOLATION TESTS PASSED SUCCESSFULLY! (INC-0304 Solved)

=== Running Audit Trail & Non-Repudiation Tests (INC-0318) ===
[TEST 1] Testing Audit Trail with Ticket: INC-0026
[TEST 1] PASS: TICKET_CREATED logged automatically.
[TEST 1] PASS: TICKET_CLAIMED logged with agent name and status.
[TEST 1] PASS: INTERNAL_NOTE_ADDED logged.
[TEST 1] PASS: PUBLIC_REPLY_SENT logged with status change to waiting_on_customer.
[TEST 1] PASS: CUSTOMER_REPLY_RECEIVED logged.
[TEST 2] Ticket Created At: 2026-11-21 16:35:24.335938
[TEST 2] Public Reply Sent At: 2026-11-21 16:35:24.375673
[TEST 2] Mathematical elapsed response time: 0.0397 seconds
[TEST 2] PASS: INC-0318 dispute conclusively resolved with mathematical timestamps.
[TEST 3] PASS: Audit log is strictly read-only; tampering endpoints are disallowed (405).
ALL AUDIT TRAIL TESTS PASSED SUCCESSFULLY! (INC-0318 Solved)
```

---

## 6. Next Planned Step

* **Step 4**: Pluggable Module 4 — Working Hours SLA Engine (Meera's SLA Rules).
  - Business calendar: 09:30 to 18:30, Monday to Friday. Pauses on weekends & festival holidays.
  - Priority targets: Urgent (2h reply, same day fix), Medium (4.5h reply, 3d fix), Small (1d reply, 1w fix).
  - SLA timer pause during `waiting_on_customer`.
  - Recalculation on priority change.
