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

#### Piece 1: Database Model & DTO Data Isolation Barrier
* **Data Model** (`backend/app/models.py`):
  - Table `messages`:
    - `id`: UUID (Primary Key)
    - `ticket_id`: Foreign Key (`tickets.id`)
    - `sender_type`: ENUM (`agent`, `customer`, `system`)
    - `sender_id`: VARCHAR (nullable agent ID)
    - `sender_name`: VARCHAR
    - `content`: TEXT
    - `is_private`: BOOLEAN (`True` for team internal notes, `False` for public replies)
    - `created_at`: TIMESTAMP WITH TIME ZONE
  - Ticket relationship: `messages = relationship("Message", back_populates="ticket", cascade="all, delete-orphan")`.
* **Strict DTO Serialization Isolation** (`backend/app/schemas.py`):
  - `MessageCreate`: Payload for creating messages.
  - `MessageOut`: Internal agent model containing `is_private` flag and metadata.
  - `CustomerMessageOut`: **Customer-Safe DTO** that strictly strips `is_private` and internal identifiers from output schemas entirely.

#### Piece 2: API Endpoints with Database-Level Filtering
* **Endpoints** (`backend/app/main.py`):
  - `GET /api/tickets/{ticket_id}/messages`:
    - Parameter: `scope: str = "agent"` (`agent` | `customer`).
    - **Customer View Wall**: When `scope="customer"`, the query applies `filter(Message.is_private == False)` at the database level and returns `CustomerMessageOut`. Private notes are never queried, loaded, or serialized.
    - **Agent View**: Returns all messages with clear `is_private: true` indicators.
  - `POST /api/tickets/{ticket_id}/messages`:
    - Accepts `MessageCreate`.
    - **Sanitization Guard**: If `sender_type == "customer"`, `is_private` is forcefully set to `False` (customers cannot create internal notes).
    - **Lifecycle Status Transition**:
      - If an agent sends a public reply to the customer, ticket status moves from `open` or `in_progress` to `waiting_on_customer` (supporting Meera's requirement: waiting time is paused).
      - If a customer responds, ticket status moves back to `in_progress`.
      - If an agent adds a private team note, status remains unchanged.

#### Piece 3: Frontend Dual-Mode Timeline & Composer
* **Client API** (`frontend/src/api.js`):
  - Added `fetchMessages(ticketId, scope)` and `postMessage(ticketId, messageData)`.
* **Workspace Timeline & Composer** (`frontend/src/App.jsx`):
  - **Visual Distinction for Incident Prevention**:
    - **Public Customer Replies**: Rendered with clean blue border (`💬 PUBLIC REPLY (Sent to {customer})`).
    - **Private Team Notes**: Rendered with a high-contrast amber background, lock icon `🔒 PRIVATE TEAM NOTE — INTERNAL ONLY`, and explicit notice that it is never shown to customers.
  - **Dual-Mode Composer Tabs**:
    - Mode 1: `💬 Reply to Customer` (Blue theme: "Send Customer Reply"). Displays an info banner reminding the agent this message goes to the customer.
    - Mode 2: `🔒 Private Team Note (Internal)` (Amber theme: "Save Internal Note"). Displays a security banner assuring the agent this note is internal only.
* **Styles** (`frontend/src/index.css`):
  - Added CSS classes for `.conversation-section`, `.message-card-public`, `.message-card-private`, `.private-note-badge`, `.composer-mode-bar`, `.mode-public-active`, and `.mode-private-active`.

#### Piece 4: Automated Verification Test Suite
* **Test Suite** (`backend/tests/test_note_isolation.py`):
  - `test_customer_view_strictly_omits_private_notes`: Verifies private note content never appears in customer query responses or raw response text.
  - `test_customer_cannot_spoof_private_notes`: Verifies customers cannot create private notes.
  - `test_lifecycle_status_transitions_on_messages`: Verifies ticket moves to `waiting_on_customer` on public agent reply, and returns to `in_progress` on customer reply.

---

## 4. Verification Test Results (Step 1 & Step 2)

```
=== Running Atomic Ticket Claiming Verification Tests ===
[TEST 1] Created fresh ticket: INC-0013
[TEST 1] Response status codes: 409 and 200
[TEST 1] PASS: Ticket INC-0013 safely assigned to Ravi with status 'in_progress'
[TEST 2] PASS: Subsequent claim rejected with 409
[TEST 3] PASS: Invalid agent returned 404
[TEST 4] PASS: Nonexistent ticket returned 404
ALL ATOMIC CLAIMING TESTS PASSED SUCCESSFULLY! (INC-0291 Solved)

=== Running Note Isolation & Security Tests (INC-0304) ===
[TEST 1] Testing with Ticket: INC-0010
[TEST 1] Customer scope returned 1 messages
[TEST 1] PASS: Zero leakage in customer API response! Private note strictly omitted.
[TEST 1] Agent scope returned 2 messages
[TEST 1] PASS: Agent correctly sees both internal notes and public replies.
[TEST 2] PASS: Customer cannot force is_private=True (sanitized to False).
[TEST 3] PASS: Status moved to 'waiting_on_customer' after public agent reply.
[TEST 3] PASS: Status returned to 'in_progress' when customer responded.
ALL NOTE ISOLATION TESTS PASSED SUCCESSFULLY! (INC-0304 Solved)
```

---

## 5. Next Planned Step

* **Step 3**: Pluggable Module 3 — Immutable Audit Event Sourcing (`INC-0318`).
  - Append-only event history logging every action (creation, claim, replies, notes, status changes).
  - Proof and non-repudiation recording who did what and when.
