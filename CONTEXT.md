# Project Context & Implementation Record

> **System**: Frontdesk Support Portal  
> **Company**: Arvo Systems (iNav Technologies)  
> **Documentation Standard**: Strict adherence to hiring specification and modular implementation guidelines.

---

## 1. Context & Background

Arvo Systems operates with nine support agents handling approximately 40 customer tickets daily. The previous shared spreadsheet and WhatsApp workflow broke down due to lack of concurrency control, data leakage, and untracked response times.

### Incident INC-0291 (14 October) — Problem Addressed in Step 1
* **Incident Summary**: Two support agents simultaneously opened the same customer ticket, clicked "take this ticket", and replied within one minute of each other with conflicting advice.
* **Root Cause**: The shared spreadsheet allowed simultaneous modifications with no mutual exclusion or atomic locking.
* **Objective for Step 1**: Build a pluggable, race-condition-proof atomic claiming mechanism so only one agent can claim a ticket. If another agent attempts to claim it concurrently, the system must immediately reject the second request with an `HTTP 409 Conflict` and display the winning assignee.

---

## 2. Step 1: Implementation Breakdown

To ensure zero bloat, high resilience, and clean separation of concerns, Step 1 was divided into 4 discrete implementation pieces:

### Piece 1: Backend DTO & Atomic Concurrency Endpoint
* **Schema** (`backend/app/schemas.py`):
  - Defined `ClaimRequest` Pydantic model (`agent_id: str`).
* **Endpoint** (`backend/app/main.py`):
  - Added `POST /api/tickets/{ticket_id}/claim`.
  - Performs validation: validates agent existence (404) and ticket existence (404).
  - Pre-check: If ticket already has an `assigned_agent_id`, immediately rejects with `HTTP 409 Conflict` naming the current agent.
  - **Atomic SQL conditional update**:
    ```python
    result = db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.assigned_agent_id.is_(None))
        .values(assigned_agent_id=payload.agent_id, status="in_progress")
    )
    ```
  - **Race Condition Guard**: If `result.rowcount == 0` (meaning a competing transaction claimed the ticket in the millisecond window between the read and update), the transaction rolls back and returns `HTTP 409 Conflict` with the actual assignee.

### Piece 2: Frontend UI & Real-Time Conflict Handling
* **API Client** (`frontend/src/api.js`):
  - Added `claimTicket(ticketId, agentId)` with 409 detail parsing.
* **Workspace View** (`frontend/src/App.jsx`):
  - When an unassigned ticket is viewed, a clear claim banner is displayed:  
    `[ ✋ Take this ticket as {CurrentAgent} ]`
  - When assigned, the banner disappears, and the assignee is prominently shown in the header.
  - **Conflict Resilience**: If a 409 Conflict occurs (another agent took it first), an alert explains the conflict, and the UI immediately re-fetches the ticket to reflect the latest assignee without crashing.
* **Styling** (`frontend/src/index.css`):
  - Added styling for `.claim-banner`, `.claim-banner-text`, and `.btn-claim`.

### Piece 3: Automated Concurrency Verification Suite
* **Test Suite** (`backend/tests/test_atomic_claim.py`):
  - Created a test simulating 2 concurrent threads firing simultaneously at the exact same millisecond against an unclaimed ticket.
  - Asserted that status codes are strictly `[200, 409]` (exactly one winner, exactly one conflict).
  - Verified subsequent claim attempts return `409 Conflict`.
  - Verified invalid agent returns `404`.
  - Verified nonexistent ticket returns `404`.

### Piece 4: Build Verification
* Frontend production build: Bundled in 597ms with 0 warnings/errors.
* Backend server: Running healthily on port 8000.
* Vite dev server: Running with reverse proxy on port 5173.

---

## 3. Files Created / Modified in Step 1

| File | Change Type | Purpose |
|---|---|---|
| `backend/app/schemas.py` | Modified | Added `ClaimRequest` Pydantic model |
| `backend/app/main.py` | Modified | Added atomic conditional update endpoint `POST /api/tickets/{ticket_id}/claim` |
| `backend/requirements.txt` | Modified | Added `requests>=2.31.0` for automated testing |
| `frontend/src/api.js` | Modified | Added `claimTicket` API function |
| `frontend/src/App.jsx` | Modified | Added claim action banner, error alert, and auto-reload logic |
| `frontend/src/index.css` | Modified | Added styles for claim action banner and buttons |
| `backend/tests/test_atomic_claim.py` | Created | Concurrency stress test verifying INC-0291 resolution |
| `CONTEXT.md` | Created | Full technical context and implementation record |

---

## 4. Verification Test Results

```
=== Running Atomic Ticket Claiming Verification Tests ===

[TEST 1] Created fresh ticket: INC-0007
[TEST 1] Response status codes: 409 and 200
[TEST 1] Conflict message: {'detail': 'Ticket has already been claimed by Ravi.'}
[TEST 1] PASS: Ticket INC-0007 safely assigned to Ravi with status 'in_progress'
[TEST 2] PASS: Subsequent claim rejected with 409: Ticket has already been claimed by Meera.
[TEST 3] PASS: Invalid agent returned 404
[TEST 4] PASS: Nonexistent ticket returned 404

ALL ATOMIC CLAIMING TESTS PASSED SUCCESSFULLY! (INC-0291 Solved)
```

---

## 5. Next Planned Step

* **Step 2**: Pluggable Module 2 — Dual-Mode Messaging & Note Isolation (`INC-0304`).
  - Separation of public customer replies vs private internal team notes.
  - Strict DTO filtering to prevent private notes from ever reaching customer screens, APIs, or exports.
