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

## 5. Step 4: Pluggable Module 4 — Working Hours SLA Engine (`INC-0327`)

### Incident / Requirement Addressed — Meera's SLA Rules & The Unanswered Meeting Question
* **Context**: Arvo Systems operates strictly on Indian business hours (09:30 to 18:30, Monday through Friday, 9 working hours = 540 min/day).
* **Key SLA Targets**:
  - **Urgent**: First reply within 2 working hours (120 min), Fix same working day (18:30).
  - **Medium**: First reply within half working day (4.5 hours = 270 min), Fix within 3 working days (1620 min).
  - **Small**: First reply within 1 working day (9 hours = 540 min), Fix within 1 working week (5 working days = 2700 min).
* **Timer Freezing Rule (REQ-SLA-03)**:
  - While a ticket is `waiting_on_customer`, the SLA clock is paused completely.
  - When the customer replies, the clock unpauses and deadlines are extended by the exact working duration paused.
* **The Unanswered Meeting Question Resolved (REQ-SLA-06)**:
  - *"What happens to the timer if we change a ticket to urgent in the middle?"*
  - **Resolution**: Dynamically recalculates remaining deadlines from the escalation timestamp. If the first response has not yet occurred, response deadline is capped to the urgent SLA; resolution deadline is immediately adjusted to the new target from escalation time. Every escalation is logged in the immutable audit trail.

### Implementation Pieces:

#### Piece 1: Pure Business Hours Calculation Engine (`backend/app/sla.py`)
- Independent, pure Python module.
- Working window: `09:30 - 18:30`, `Monday - Friday`.
- Pre-seeded 2026 festival holidays (Republic Day, Holi, Good Friday, May Day, Independence Day, Gandhi Jayanti, Diwali, Christmas, etc.).
- Functions:
  - `is_business_day(date, holidays)`: Checks weekday < 5 and holiday exclusion.
  - `next_business_start(dt, holidays)`: Jumps to 09:30 on next valid working day.
  - `add_business_minutes(start_dt, minutes)`: Advances time through business windows, skipping off-hours, weekends, and holidays.
  - `calculate_business_minutes_between(start_dt, end_dt)`: Calculates exact working minutes elapsed.
  - `compute_ticket_slas(created_at, priority)`: Sets initial response and resolution deadlines.
  - `recalculate_sla_on_priority_change(current_time, new_priority, first_responded_at)`: Dynamically handles mid-lifecycle escalation.
  - `compute_sla_status(ticket, current_time)`: Real-time SLA health evaluator returning badges (`sla-chip-healthy`, `sla-chip-due-soon`, `sla-chip-overdue`, `sla-chip-paused`, `sla-chip-completed`).

#### Piece 2: Database Model & DTO Extension (`backend/app/models.py`, `backend/app/schemas.py`)
- Added fields to `Ticket` model:
  - `first_response_due_at`, `resolution_due_at`, `first_responded_at`, `resolved_at`, `sla_paused_at`, `total_paused_minutes`.
- Extended `TicketOut` schema with all SLA fields + `sla_status` dictionary.
- Created `PriorityUpdateRequest` and `ResolveTicketRequest` DTOs.

#### Piece 3: API Integration & SLA Pause/Resume Lifecycle (`backend/app/main.py`)
- `POST /api/tickets`: Automatically computes and attaches SLA deadlines on creation.
- `POST /api/tickets/{id}/messages`:
  - On public agent reply: Sets `first_responded_at` (if first reply), sets `status = "waiting_on_customer"`, freezes SLA with `sla_paused_at = now`.
  - On customer reply: Calculates business minutes elapsed while paused, extends `resolution_due_at` accordingly, clears `sla_paused_at`, and returns ticket to `in_progress`.
- `PATCH /api/tickets/{id}/priority`: Recalculates SLA deadlines from escalation point and logs `PRIORITY_CHANGED` in audit trail.
- `POST /api/tickets/{id}/resolve`: Sets `status = "done"`, timestamps `resolved_at`, marks SLA completed, and logs `TICKET_RESOLVED` in audit trail.

#### Piece 4: Frontend SLA Badges, Panel & Actions (`frontend/src/`)
- `frontend/src/api.js`: Added `updatePriority` and `resolveTicket`.
- `frontend/src/App.jsx`:
  - Ticket Queue: Added live SLA chip (`Due in Xh Ym`, `Overdue`, `Paused`, `Resolved`) to every card.
  - Ticket Detail: Added dedicated SLA status panel displaying response deadline, resolution deadline, pause notice, and completed checkmarks.
  - Added Priority Escalation selector and "Mark as Resolved" action button.
- `frontend/src/index.css`: Added clean styling for all SLA chip states and panel layouts.

#### Piece 5: Automated Verification Test Suite (`backend/tests/test_sla_engine.py`)
- 5 comprehensive automated tests:
  1. `test_business_hours_calculations`: Verified same-day addition, Friday-to-Monday weekend skip, and Good Friday festival holiday skip.
  2. `test_ticket_creation_sets_sla_deadlines`: Verified urgent, medium, and small SLA deadlines.
  3. `test_sla_pause_and_resume_lifecycle`: Verified timer freeze on agent reply and unpause/deadline extension on customer reply.
  4. `test_priority_escalation_recalculates_sla_and_audits`: Verified mid-lifecycle escalation recalculation and audit trail entry.
  5. `test_ticket_resolution_freezes_sla`: Verified resolve marks status 'done', sets SLA state 'completed', and logs non-repudiation audit event.

---

## 6. Comprehensive Verification Test Suite Results (Steps 1, 2, 3, and 4)

```
[TEST 1] Testing Business Hours Calculation Logic...
  ✓ Same-day addition within business hours passed.
  ✓ Weekend skip (Friday -> Monday 11:00) passed.
  ✓ Festival Holiday skip (Good Friday + Weekend -> Monday 10:00) passed.
  ✓ Off-hours start advancement passed.

[TEST 2] Testing Ticket SLA Deadlines by Priority...
  ✓ Urgent ticket SLA initialized: Due in 42h 35m
  ✓ Medium ticket SLA initialized: Due in 45h 5m
  ✓ Small ticket SLA initialized: Due in 49h 35m

[TEST 3] Testing SLA Pause / Resume on Customer Inactivity...
  ✓ Ticket status moved to waiting_on_customer, SLA paused successfully.
  ✓ Customer replied, ticket moved back to in_progress and SLA resumed.

[TEST 4] Testing Mid-Lifecycle Priority Escalation...
  ✓ Priority escalated to urgent, new resolution deadline: 2026-11-23T18:30:00
  ✓ PRIORITY_CHANGED correctly recorded in immutable audit log.

[TEST 5] Testing Ticket Resolution...
  ✓ Ticket resolved successfully with SLA state 'completed'.
  ✓ TICKET_RESOLVED correctly recorded in immutable audit log.

✅ ALL STAGE 4 SLA ENGINE TESTS PASSED SUCCESSFULLY!

Regression Tests:
- Atomic Claiming (INC-0291): 4/4 PASSED
- Note Isolation & Leak Prevention (INC-0304): 5/5 PASSED
- Immutable Audit Trail (INC-0318): 3/3 PASSED
```

---

## 7. Step 5: Pluggable Module 5 — Lifecycle Policies (Inactivity Auto-Close & Reopening Guard)

### Requirements Addressed
* **REQ-SLA-04: Auto-Close Inactive Tickets**:
  - If a ticket remains in `waiting_on_customer` for $\ge$ 5 working days (45 working hours = 2,700 business minutes), the system automatically closes it.
  - Automatically emits an immutable system audit event: `AUTO_CLOSED` (*"Auto-closed due to 1 week of customer inactivity (5 working days / 45 hours)."*).
* **REQ-SLA-05: Reopening Window Guard**:
  - Customers or agents can reopen a resolved or closed ticket within 7 calendar days.
  - Reopening after 7 calendar days is strictly rejected with `HTTP 400 Bad Request`:
    > *"Tickets closed more than 1 week ago cannot be reopened. Please submit a new ticket."*
  - Reopening records `TICKET_REOPENED` in the immutable audit log and transitions status back to `in_progress`.

### Implementation Pieces:

#### Piece 1: Pure Lifecycle Policy Engine (`backend/app/lifecycle.py`)
- Independent policy service:
  - `can_reopen_ticket(ticket, current_time)`: Validates status (`done` or `closed`), computes elapsed calendar time since `resolved_at` or `closed_at`. Rejects after 7 days with the specification-required message.
  - `should_auto_close(ticket, current_time)`: Validates `waiting_on_customer` status, computes elapsed working minutes using `calculate_business_minutes_between(sla_paused_at, now)`. Flags for closure when $\ge$ 2,700 business minutes (5 working days).
  - `evaluate_auto_close_tickets(db, current_time)`: Scans eligible tickets, transitions status to `closed`, records `closed_at`, clears `sla_paused_at`, and emits `AUTO_CLOSED` system audit event.

#### Piece 2: Database Schema & API Endpoints (`backend/app/models.py`, `backend/app/schemas.py`, `backend/app/main.py`)
- Added `closed_at` column to `Ticket` model and `TicketOut` schema.
- Added `ReopenTicketRequest` DTO (`agent_id`, `reason`).
- Dynamic schema compatibility check in `lifespan` ensuring `closed_at` is safely added to existing SQLite tables.
- Endpoint `POST /api/tickets/{ticket_id}/reopen`:
  - Validates eligibility with `can_reopen_ticket`.
  - Transitions ticket back to `in_progress`, clears `resolved_at` and `closed_at`.
  - Emits `TICKET_REOPENED` audit event.
- Endpoint `POST /api/tickets/auto-close`:
  - Runs batch evaluation and auto-closes inactive tickets.
- `GET /api/tickets`: Automatically triggers `evaluate_auto_close_tickets` so queues reflect up-to-date statuses.

#### Piece 3: Frontend Reopen & Lifecycle UI (`frontend/src/`)
- `frontend/src/api.js`: Added `reopenTicket` and `triggerAutoClose`.
- `frontend/src/App.jsx`:
  - Detail Pane: When viewing a `done` or `closed` ticket, displays `🔄 Reopen Ticket` action button.
  - Reopen action prompts for an optional reason and handles rejection alerts gracefully (e.g., displaying the 7-day cutoff rule).
  - Added dedicated `🔒 Ticket Closed` banner when status is `closed`.
- `frontend/src/index.css`: Added styles for `.btn-reopen`, `.closed-banner`, `.action-ticket_reopened`, `.action-auto_closed`.

#### Piece 4: Automated Verification Test Suite (`backend/tests/test_lifecycle_policies.py`)
- 4 comprehensive tests:
  1. `test_reopen_within_seven_days_allowed`: Verified reopening resolved ticket within 7 calendar days transitions status to `in_progress` and logs `TICKET_REOPENED`.
  2. `test_reopen_after_seven_days_rejected`: Verified attempting to reopen a ticket resolved 10 days ago is rejected with `HTTP 400` and exact specification error message.
  3. `test_reopen_open_ticket_rejected`: Verified attempting to reopen an already active ticket returns `HTTP 400`.
  4. `test_auto_close_inactivity_policy`: Verified tickets waiting on customers for < 5 working days remain untouched, while tickets exceeding 5 working days (2,700 business minutes) auto-close to `closed` with `AUTO_CLOSED` audit log.

---

## 8. Comprehensive Verification Test Suite Results (Steps 1, 2, 3, 4, and 5)

```
=== Running Atomic Ticket Claiming Verification Tests ===
[TEST 1] Response status codes: 409 and 200
[TEST 1] PASS: Ticket safely assigned with status 'in_progress'
[TEST 2] PASS: Subsequent claim rejected with 409
[TEST 3] PASS: Invalid agent returned 404
[TEST 4] PASS: Nonexistent ticket returned 404
ALL ATOMIC CLAIMING TESTS PASSED SUCCESSFULLY! (INC-0291 Solved)

=== Running Note Isolation & Security Tests (INC-0304) ===
[TEST 1] PASS: Zero leakage in customer API response! Private note strictly omitted.
[TEST 1] PASS: Agent correctly sees both internal notes and public replies.
[TEST 2] PASS: Customer cannot force is_private=True (sanitized to False).
[TEST 3] PASS: Status moved to 'waiting_on_customer' after public agent reply.
[TEST 3] PASS: Status returned to 'in_progress' when customer responded.
ALL NOTE ISOLATION TESTS PASSED SUCCESSFULLY! (INC-0304 Solved)

=== Running Audit Trail & Non-Repudiation Tests (INC-0318) ===
[TEST 1] PASS: TICKET_CREATED, TICKET_CLAIMED, INTERNAL_NOTE_ADDED, PUBLIC_REPLY_SENT, CUSTOMER_REPLY_RECEIVED logged.
[TEST 2] PASS: INC-0318 dispute conclusively resolved with mathematical timestamps.
[TEST 3] PASS: Audit log is strictly read-only; tampering endpoints are disallowed (405).
ALL AUDIT TRAIL TESTS PASSED SUCCESSFULLY! (INC-0318 Solved)

=== Running Working Hours SLA Tests (INC-0327) ===
[TEST 1] ✓ Same-day addition, weekend skip, and festival holiday skip passed.
[TEST 2] ✓ Urgent, medium, and small SLA deadlines computed correctly.
[TEST 3] ✓ SLA paused on waiting_on_customer, resumed on customer reply.
[TEST 4] ✓ Mid-lifecycle priority escalation recalculated SLA and logged PRIORITY_CHANGED.
[TEST 5] ✓ Ticket resolution marked status 'done' and froze SLA as 'completed'.
ALL STAGE 4 SLA ENGINE TESTS PASSED SUCCESSFULLY!

=== Running Lifecycle Inactivity & Reopening Policy Tests (REQ-SLA-04 & REQ-SLA-05) ===
[TEST 1] ✓ Ticket reopened successfully within 7 days, logged TICKET_REOPENED.
[TEST 2] ✓ Reopening after 7 days strictly rejected with HTTP 400: 'Tickets closed more than 1 week ago cannot be reopened. Please submit a new ticket.'
[TEST 3] ✓ Rejecting reopen on active ticket passed.
[TEST 4] ✓ Tickets waiting on customers >= 5 working days auto-closed to 'closed' and logged AUTO_CLOSED.
ALL STAGE 5 LIFECYCLE POLICY TESTS PASSED SUCCESSFULLY!
```

---

## 9. Senior Engineer Deep Edge Case Analysis & Hardening

### Overview
A comprehensive boundary, concurrency, and security audit was executed across all application layers to uncover latent edge cases, race conditions, and policy bypass vulnerabilities.

### Discovered Edge Cases & Applied Fixes:
1. **Terminal State Claiming Loophole**:
   - *Bug*: A ticket that had already been resolved (`done`) or `closed` could be directly claimed by an agent, illegally bypassing the 7-day reopen guard and reverting status to `in_progress`.
   - *Fix applied*: Added explicit terminal state verification in `claim_ticket`. Attempting to claim a resolved/closed ticket returns `HTTP 400 Bad Request` (*"Cannot claim a resolved or closed ticket. Reopen the ticket first."*).
2. **Whitespace / Empty Message Injection**:
   - *Bug*: `post_ticket_message` accepted empty strings or whitespace-only messages.
   - *Fix applied*: Validates `payload.content.strip()`. Empty or whitespace messages are rejected with `HTTP 400 Bad Request` (*"Message content cannot be empty."*).
3. **Closed Ticket Customer Messaging Guard**:
   - *Bug*: A customer could post a message on a ticket closed more than 7 days ago, circumventing the REQ-SLA-05 reopen window guard.
   - *Fix applied*: Checked `can_reopen_ticket` when a customer message is posted to a terminal ticket. If closed $> 7$ days, rejected with `HTTP 400` (*"Tickets closed more than 1 week ago cannot be reopened. Please submit a new ticket."*). If within 7 days, posting customer message safely transitions the ticket back to `in_progress`.
4. **Priority Escalation on Resolved Tickets**:
   - *Bug*: `update_ticket_priority` allowed escalating an already resolved ticket, re-activating recalculation logic on frozen SLAs.
   - *Fix applied*: Blocked with `HTTP 400` (*"Cannot change priority of a resolved or closed ticket."*).
5. **Double-Resolution Reset Vulnerability**:
   - *Bug*: Repeated calls to `/resolve` on an already `done` ticket reset `resolved_at` to the current timestamp, inadvertently resetting the 7-day reopen countdown.
   - *Fix applied*: Blocked with `HTTP 400` (*"Ticket is already resolved or closed."*), preserving the original timestamp.
6. **High Concurrency Contention (N=5 simultaneous agents)**:
   - Verified with 5 simultaneous threads competing for a single ticket. Exactly one agent receives `200 OK`, while all other 4 agents receive `409 Conflict`.
7. **Exact Working-Hours Arithmetic & Weekend Pause**:
   - Verified that weekend pauses calculate strictly 60 business minutes (not 64 hours).
   - Verified exact 2,699 business minutes does not trigger auto-close, whereas exact 2,700 business minutes (5 working days) triggers auto-close.

### Edge Case Verification Output:
```text
[EDGE 1] High Concurrency Claiming (5 simultaneous agents)...
  ✓ Status codes from 5 simultaneous workers: [200, 409, 409, 409, 409]
  ✓ Safely claimed by winner: Meera

[EDGE 2] Claiming Guards on Terminal States...
  ✓ Claiming resolved/closed ticket rejected with HTTP 400.

[EDGE 3] Messaging Boundary & Security Leak Guards...
  ✓ Empty / whitespace message rejected with HTTP 400.
  ✓ Customer scope strictly filters private notes and omits is_private field.
  ✓ Customer messaging on ticket closed > 7 days rejected with HTTP 400.

[EDGE 4] SLA Exact Boundary Arithmetic...
  ✓ Exact business start (09:30) addition passed.
  ✓ Exact business end (18:30) rollover passed.
  ✓ Paused duration across weekend is exactly 60 business minutes (not 64 hours).
  ✓ Multi-day holiday span correctly skips Good Friday + Weekend.

[EDGE 5] Priority Escalation Guards...
  ✓ Invalid priority string rejected with HTTP 400.
  ✓ Priority escalation on resolved ticket rejected with HTTP 400.

[EDGE 6] Lifecycle Reopening Boundary Conditions (6d23h vs 7d1h)...
  ✓ Reopen at 6 days 23 hours allowed successfully.
  ✓ Reopen at 7 days 1 hour rejected with HTTP 400.

[EDGE 7] Auto-Close Inactivity Exact Business Minutes Threshold...
  ✓ Ticket at 2,699 business minutes does NOT auto-close.
  ✓ Ticket at exact 2,700 business minutes (5 working days) triggers auto-close.

[EDGE 8] Audit Log Immutability & Monotonicity...
  ✓ PUT, PATCH, DELETE on audit endpoint return 405 Method Not Allowed.
  ✓ Audit logs are strictly monotonically ordered by ID and timestamp.

🌟 ALL SENIOR ENGINEER EDGE CASE TESTS COMPLETED!
```

---

## 10. Next Planned Step

* **Step 6**: Packaging & Deployment.
  - Production containerization & startup script.
  - Comprehensive documentation & user guide.
  - Evaluation summary.





---

# Frontdesk v2 Implementation Log: Authentication & Real-Time SSE Push

**Date**: 2026-11-21  
**Author**: Antigravity Engineering  
**Scope**: Full Stack Developer Hiring Test — Authentication & Real-Time Push Streaming

## 1. Components Implemented

### A. Authentication Module (`backend/app/auth.py`)
- **Password Hashing**: Direct `argon2-cffi` PasswordHasher (OWASP parameters: memory=64MB, parallelism=2, time_cost=2). Zero reliance on unmaintained passlib.
- **JWT Token Management**: HMAC-SHA256 tokens using `pyjwt` with 8-hour expiration. Payload contains `sub` (agent UUID), `email`, `role`, and UTC timestamps (`iat`, `exp`).
- **Customer Magic Link Tokens**: Deterministic `HMAC-SHA256(ticket_id + customer_email, SECRET_KEY)` hex digest enabling secure, zero-password customer access. Constant-time comparison prevents timing attacks.
- **FastAPI Dependency (`get_current_agent`)**:
  - Supports Bearer token in `Authorization` header and `?token=` query parameter (vital for browser EventSource API).
  - Validates cryptographic signature and expiration on provided tokens.
  - Development fallback: when `REQUIRE_AUTH=false` and no credentials supplied, falls back to the lead agent, ensuring 100% backward compatibility for all Stage 0–5 tests.

### B. Real-Time Push Streaming (`backend/app/events.py`)
- **Pub/Sub Broadcaster (`EventBroadcaster`)**: Pure in-process asyncio event hub with per-subscriber bounded `asyncio.Queue` (capacity 100) and automatic slow-consumer drops.
- **SSE Stream (`GET /api/events/stream`)**: FastAPI `StreamingResponse` with `text/event-stream` mime-type, immediate `CONNECTED` handshake, and 20-second keepalive pings.
- **Broadcast Integration**:
  - `TICKET_CLAIMED`: Dispatched immediately upon atomic claim.
  - `PUBLIC_REPLY_SENT` / `CUSTOMER_REPLY_RECEIVED`: Dispatched on communication events (strictly omitting internal notes).
  - `TICKET_RESOLVED`: Dispatched when ticket transitions to resolved status.

### C. Database & Schema Migrations
- **Agent Schema**: Added `password_hash` (VARCHAR 255), `is_active` (BOOLEAN), and `last_login_at` (DATETIME).
- **Ticket Schema**: Added `customer_token_hash` (VARCHAR 64).
- **Idempotent Lifespan Migrations**: Executed via SQLite PRAGMA checks and `ALTER TABLE` statements without destroying existing state.
- **Seed Data**: Upgraded all 9 agents with default Argon2id password hash (`arvo2026!`).

### D. Frontend Interface (`frontend/src/`)
- **API Client (`api.js`)**: Added `loginAgent`, `logoutAgent`, and `getMe` with Bearer auth header injection.
- **Custom React Hook (`useEventStream.js`)**: Manages browser `EventSource` connection, event deserialization, and automatic reconnection.
- **UI Integrations (`App.jsx`, `index.css`)**:
  - Added live status pill (`🟢 Live` / `⚪ Connecting…`).
  - Added Agent Sign-In modal with instant validation and error handling.
  - Automatic queue and ticket detail refresh on incoming SSE events.

## 2. Test Verification Matrix
- **AUTH-01 to AUTH-06**: Valid login, invalid credentials (401), non-existent agent (401), tampered/expired JWT rejection (401), strict mode enforcement, and customer magic link security.
- **PUSH-01 to PUSH-04**: SSE text/event-stream content negotiation, broadcaster queue fan-out, queue overflow resilience, and non-blocking background broadcasting.
- **REG-01**: Verified all previous stages (Stages 0–5) remain 100% operational with zero regressions.
- **Vite Production Build**: Verified bundle compiles without warnings or errors.


---

# Frontdesk v3 Implementation Log: Phase 1 (Backend Modularization)

**Date**: 2026-11-22  
**Author**: Antigravity Engineering  
**Scope**: Enterprise Production Architecture — Phase 1: Backend Decomposition & Router Restructuring

## 1. Architectural Changes Implemented

### A. Core Architecture Layer (`backend/app/core/`)
- **`config.py`**: Centralized application configuration with typed `Settings` object managing `SECRET_KEY`, `ALGORITHM`, `TOKEN_EXPIRE_HOURS`, `REQUIRE_AUTH`, and `DATABASE_URL`.
- **`security.py`**: Extracted all cryptographic primitives (`Argon2id` password hasher with OWASP parameters, `pyjwt` HMAC-SHA256 generation/decoding, and deterministic customer magic link HMAC tokens).
- **`dependencies.py`**: Extracted global FastAPI dependencies (`get_db`, `get_current_agent`, `get_effective_agent`, and `verify_ticket_ownership`).

### B. Modular API Controllers (`backend/app/api/v1/`)
- Decomposed monolithic `main.py` (> 740 lines) into dedicated, decoupled FastAPI `APIRouter` modules:
  - **`api/health.py`**: Standalone health check controller (`/api/health`).
  - **`api/v1/auth.py`**: Authentication endpoints (`POST /api/auth/login`, `GET /api/auth/me`).
  - **`api/v1/agents.py`**: Team directory endpoints (`GET /api/agents`).
  - **`api/v1/tickets.py`**: Ticket lifecycle & mutation operations (`GET/POST /api/tickets`, `/claim`, `/priority`, `/resolve`, `/reopen`, `/auto-close`).
  - **`api/v1/messages.py`**: Dual-mode communication feed & private note isolation (`GET/POST /api/tickets/{id}/messages`).
  - **`api/v1/audit.py`**: Read-only append-only audit trail (`GET /api/tickets/{id}/audit`).
  - **`api/v1/events.py`**: SSE real-time push streaming (`GET /api/events/stream`).
  - **`api/v1/router.py`**: Central v1 aggregator routing all domain controllers under `/api`.

### C. Ultra-Lean Entrypoint (`backend/app/main.py`)
- Reduced `main.py` from 740+ lines down to 65 clean lines.
- Responsibilities strictly confined to lifespan schema migrations, CORS middleware, and mounting routers.

### D. Zero-Regression Backward-Compatibility Bridge
- Updated `backend/app/auth.py` as an exported facade referencing the new `core/` modules.
- Preserved 100% compatibility for external scripts and existing automated test suites importing from `app.auth`, `app.sla`, `app.lifecycle`, and `app.events`.

## 2. Test Verification Matrix
- All 7 test suites executed and verified passing at 100%:
  - `test_atomic_claim.py`: 4/4 Passed
  - `test_note_isolation.py`: 5/5 Passed
  - `test_audit_trail.py`: 3/3 Passed
  - `test_sla_engine.py`: 5/5 Passed
  - `test_lifecycle_policies.py`: 4/4 Passed
  - `test_senior_engineer_edge_cases.py`: 8/8 Passed
  - `test_auth_and_push.py`: 29/29 Passed (including new RBAC ticket ownership tests)


---

# Frontdesk v3 Implementation Log: Phase 2 (Design Tokens & Reusable UI Primitives)

**Date**: 2026-11-22  
**Author**: Antigravity Engineering  
**Scope**: Enterprise Production Architecture — Phase 2: Design Tokens & Reusable UI Primitives

## 1. Architectural Changes Implemented

### A. Centralized Design Tokens (`frontend/src/styles/tokens.css`)
- **Color Palettes**:
  - Full Brand Primary palette (`--brand-50` through `--brand-900`).
  - Slate/Zinc Neutrals (`--slate-50` through `--slate-950`).
  - Semantic priority color pairs (Urgent: Crimson, Medium: Amber, Small: Emerald).
  - Semantic status color pairs (Open, In Progress, Waiting on Customer, Done, Closed).
- **Elevation & Radii**:
  - Layered drop shadows (`--shadow-xs` to `--shadow-xl`).
  - Standardized border radiuses (`--radius-xs` to `--radius-full`).
  - Global CSS keyframe animations: `@keyframes pulseBeacon`, `@keyframes fadeInOverlay`, `@keyframes scaleInModal`, `@keyframes spin`.

### B. Common Reusable Component Library (`frontend/src/components/common/`)
- **`Button.jsx`**: Polymorphic button component with variants (`primary`, `secondary`, `danger`, `success`, `ghost`), sizes (`sm`, `md`, `lg`), loading spinner indicator, and icon slot.
- **`Badge.jsx`**: Standardized semantic badge with color dot indicator for priorities and status labels.
- **`StatusPill.jsx`**: Live SSE push streaming indicator featuring real-time pulsating beacon.
- **`Modal.jsx`**: Accessible modal dialog with backdrop-blur, `Escape` key capture, click-outside dismissal, and scale-in transition.
- **`Input.jsx`**: Standardized form input and multiline textarea supporting labels, required markers, error banners, and helper hints.
- **`EmptyState.jsx`**: Clean placeholder component with icon, heading, description, and optional call-to-action button.
- **`index.js`**: Barrel exporter for streamlined component imports across the application.

### C. Design Primitives Stylesheet (`frontend/src/styles/components.css`)
- Implemented isolated, token-driven component rules for all common primitives.
- Integrated into `index.css` with zero breakage to legacy dashboard styling.

## 2. Verification
- `npm run build` compiled successfully in 1.70s with 0 errors.
- All styles and tokens cleanly bundled.


---

# Frontdesk v3 Implementation Log: Phase 3 (Login Gateway & Component Decomposition)

**Date**: 2026-11-22  
**Author**: Antigravity Engineering  
**Scope**: Enterprise Production Architecture — Phase 3: Login Gateway & Component Decomposition

## 1. Architectural Changes Implemented

### A. Centralized Authentication Context & Hook (`frontend/src/context/`, `frontend/src/hooks/`)
- **`AuthContext.jsx`**: Global authentication context managing reactive session state (`user`, `token`, `isAuthenticated`, `isLoading`), persistent `localStorage` synchronization, `login(email, password)`, `loginAs(email)`, and `logout()`.
- **`useAuth.js`**: Clean consumer hook granting unified access to auth state across all components.

### B. Dedicated Login-First Gateway Screen (`frontend/src/components/auth/`, `frontend/src/styles/auth.css`)
- **`LoginPage.jsx`**: High-end enterprise split screen:
  - **Left Brand Hero**: Deep slate styling (`#0f172a`), emblem, Indian business-hours SLA engine description (09:30 - 18:30 IST), and security credentials badge (Argon2id + JWT).
  - **Right Authentication Card**: Clean input controls with validation and error alerts.
  - **1-Click Demo Profiles**: Quick-switch cards for immediate testing as Meera (Lead), Ravi (Senior Agent), Priya (Agent), Arjun (Restricted Agent), or Sneha (Agent).
- **`App.jsx` Gateway Routing**:
  - Replaced 800+ lines of monolithic code with an ultra-lean (< 40 lines) gateway router.
  - Unauthenticated visitors are strictly presented with `LoginPage` as the very first screen.

### C. Component Decomposition (`frontend/src/components/`)
- **`layout/Navbar.jsx`**: Brand badge, live pulsating SSE `StatusPill`, active agent avatar/role pill, and sign-out action.
- **`layout/DashboardLayout.jsx`**: Container orchestrating the master-detail split layout and real-time SSE stream events.
- **`tickets/TicketQueue.jsx`**: Feed header, status filter pills, and scrollable ticket card list.
- **`tickets/TicketCard.jsx`**: Row item with priority badges, status badges, and SLA health indicators.
- **`tickets/SlaPanel.jsx`**: Indian business calendar SLA countdowns, first response due, resolution due, and customer wait pause banners.
- **`tickets/TicketDetail.jsx`**: Inspector pane with description, customer metadata, RBAC-guarded priority/resolve/reopen actions, conversation feed, and dual-mode message composer.
- **`tickets/CreateTicketModal.jsx`**: New ticket submission dialog built with reusable `Modal`, `Input`, and `Button` primitives.
- **`tickets/AuditLogModal.jsx`**: Chronological event sourcing ledger viewer for non-repudiation.

## 2. Verification
- `npm run build` compiled 48 modules in 1.26s with 0 errors.
- All 7 test suites (29 auth/push tests + 29 core regression tests) verified passing at 100%.
