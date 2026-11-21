# Frontdesk: Comprehensive System Architecture & Build Plan

> **Source of Truth**: *iNav Technologies / Arvo Systems Hiring Test Document (Date: 21-11-2026)*  
> **Target**: Support ticket management platform replacing shared spreadsheet & WhatsApp group.

---

## 1. Specification Breakdown & Requirements Traceability

Every requirement below is drawn directly from the meeting notes (Meera, Support Lead) and the three incident reports.

| Requirement ID | Source in Document | Exact Need / Requirement | Why It Is Required (Rationale) |
|---|---|---|---|
| **REQ-SLA-01** | Meeting Notes (§3) | Working Hours SLA: 09:30 to 18:30, Mon–Fri. Timer pauses on weekends & festival holidays. | Spreadsheet counted clock hours over weekends, falsely flagging tickets arriving 6 PM Friday as late on Sunday. |
| **REQ-SLA-02** | Meeting Notes (§3) | Tiered Response & Resolution SLAs: <br>• **Urgent (cannot work)**: 2h reply, same working day fix.<br>• **Medium**: half-day reply (4.5h), 3 working days fix.<br>• **Small (questions)**: 1 working day reply (9h), 1 working week fix (5 days). | Align expectations and SLA tracking with severity of customer disruption. |
| **REQ-SLA-03** | Meeting Notes (§3) | SLA Timer Pause: Timer freezes when waiting for customer response; unfreezes on customer reply. | Agents unfairly penalized for long customer response times ("That week is not our fault"). |
| **REQ-SLA-04** | Meeting Notes (§3) | Auto-Close Inactive Tickets: If customer does not reply for ~1 working week (5 working days), auto-close ticket. | Prevents abandoned tickets from lingering indefinitely in active queues. |
| **REQ-SLA-05** | Meeting Notes (§3) | Reopen Window: Customer can reopen a closed ticket within 1 week; after 1 week, system requires a new ticket. | Balances customer convenience with ticket state finality. |
| **REQ-SLA-06** | Meeting Notes (§3) | Priority Escalation Policy (Unanswered Question): Recalculate SLA clock dynamically upon severity change. | Resolves the unresolved meeting discussion regarding mid-lifecycle priority changes. |
| **REQ-AGENT-01**| Meeting Notes (§3) | Single-Screen Agent Dashboard: View all assigned/unassigned tickets, real-time SLA status (Overdue, Due Soon, Waiting on Customer). | Eliminates context switching; agents need immediate visibility of overdue & blocked work. |
| **REQ-AGENT-02**| Meeting Notes (§3) | Dual-Mode Communication: Ability to send public reply to customer OR write private team-only note. | Agents' sole primary workflow: replying or internal coordination. |
| **REQ-LOCK-01** | Incident INC-0291 (§4.1) | Atomic Ticket Claiming: Mutual exclusion when clicking "Take this ticket". | Prevents two agents claiming and replying concurrently with conflicting instructions. |
| **REQ-SEC-01**  | Incident INC-0304 (§4.2) | Private Note Data Isolation: Private notes must never be exposed to customer (API, UI, export, list). | Severe confidentiality breach occurred when internal advice was sent to customer. |
| **REQ-AUDIT-01**| Incident INC-0318 (§4.3) | Immutable, Append-Only Audit Trail: Log who did what, when, and exact change history. Non-editable. | Resolves disputes regarding whether SLA was met and who replied when. |

---

## 2. Technical Stack Selection & Justification

| Layer | Selected Tech | Rationale & Documentation Fit |
|---|---|---|
| **Backend** | **Python (FastAPI)** | High performance, native async support, strict request/response DTO schemas (Pydantic) ensuring zero leakage of private notes, easy date/time arithmetic for working hours. |
| **Database** | **PostgreSQL** (or SQLite in dev, PostgreSQL on deploy) | Native ACID transactions with `SELECT ... FOR UPDATE` (or atomic conditional `UPDATE`) for concurrency lock (INC-0291), robust JSONB for audit snapshots. |
| **ORM / Migration** | **SQLAlchemy 2.0 + Alembic** | Schema safety, strict relation definitions, migration tracking. |
| **Frontend** | **React (Vite) + Tailwind CSS** | Clean single-screen support interface, distinct visual styling for private notes vs public replies, responsive layout. |
| **Hosting** | **Render / Railway / Fly.io** | Satisfies requirement for free tier online browser-accessible hosting. |

---

## 3. Detailed Data Models & Schema Design

### 3.1 `agents`
* `id`: UUID (Primary Key)
* `name`: VARCHAR(100) (e.g., Meera, Support Agent 1..9)
* `email`: VARCHAR(150) UNIQUE
* `role`: VARCHAR(20) (`agent`, `lead`, `admin`)
* `created_at`: TIMESTAMP WITH TIME ZONE

### 3.2 `tickets`
* `id`: VARCHAR(20) (e.g. `INC-0319`)
* `title`: VARCHAR(255)
* `description`: TEXT
* `customer_id`: VARCHAR(100)
* `customer_name`: VARCHAR(100)
* `customer_email`: VARCHAR(150)
* `priority`: ENUM (`urgent`, `medium`, `small`)
* `status`: ENUM (`open`, `in_progress`, `waiting_on_customer`, `done`, `closed`)
* `assigned_agent_id`: UUID (Foreign Key -> `agents.id`, NULLABLE)
* `version`: INTEGER DEFAULT 1 (Optimistic lock version)
* `created_at`: TIMESTAMP WITH TIME ZONE
* `first_response_due_at`: TIMESTAMP WITH TIME ZONE (Calculated based on business hours)
* `resolution_due_at`: TIMESTAMP WITH TIME ZONE (Calculated based on business hours)
* `first_responded_at`: TIMESTAMP WITH TIME ZONE (NULLABLE)
* `resolved_at`: TIMESTAMP WITH TIME ZONE (NULLABLE)
* `closed_at`: TIMESTAMP WITH TIME ZONE (NULLABLE)
* `sla_paused_at`: TIMESTAMP WITH TIME ZONE (NULLABLE - when status entered `waiting_on_customer`)
* `total_paused_business_seconds`: INTEGER DEFAULT 0

### 3.3 `messages` (Public Responses & Private Notes)
* `id`: UUID (Primary Key)
* `ticket_id`: VARCHAR(20) (Foreign Key -> `tickets.id`)
* `sender_type`: ENUM (`customer`, `agent`, `system`)
* `sender_id`: VARCHAR(100) (Agent UUID, customer email, or system)
* `sender_name`: VARCHAR(100)
* `content`: TEXT
* `is_private`: BOOLEAN DEFAULT FALSE (Crucial: Private team note flag)
* `created_at`: TIMESTAMP WITH TIME ZONE

### 3.4 `audit_logs` (Append-Only Event Sourcing)
* `id`: BIGSERIAL (Primary Key)
* `ticket_id`: VARCHAR(20) (Foreign Key -> `tickets.id`)
* `actor_type`: ENUM (`agent`, `customer`, `system`)
* `actor_id`: VARCHAR(100)
* `actor_name`: VARCHAR(100)
* `action`: VARCHAR(50) (e.g., `TICKET_CREATED`, `TICKET_CLAIMED`, `PUBLIC_REPLY_SENT`, `INTERNAL_NOTE_ADDED`, `STATUS_CHANGED`, `PRIORITY_CHANGED`, `TICKET_RESOLVED`, `TICKET_REOPENED`, `AUTO_CLOSED`)
* `details`: JSONB (Before/After delta, snapshot)
* `created_at`: TIMESTAMP WITH TIME ZONE DEFAULT NOW()
*(Note: No update or delete operations will be exposed on this table)*

### 3.5 `holidays`
* `date`: DATE (Primary Key)
* `name`: VARCHAR(100) (e.g. Festival holidays)

---

## 4. Deep-Dive Solution for Critical Document Incidents

### 4.1 Solution for INC-0291 (Atomic Claiming / Race Condition Prevention)
* **Vulnerability**: Two agents open ticket simultaneously and click "Take this ticket".
* **Fool-Proof Mitigation**:
  1. Atomic SQL statement with row lock or condition:
     ```sql
     UPDATE tickets 
     SET assigned_agent_id = :agent_id, 
         status = 'in_progress', 
         version = version + 1
     WHERE id = :ticket_id AND assigned_agent_id IS NULL;
     ```
  2. If affected row count is `0`, backend returns `HTTP 409 Conflict` with:
     ```json
     {
       "error": "TICKET_ALREADY_CLAIMED",
       "message": "This ticket has already been taken by another agent."
     }
     ```
  3. Frontend immediately updates the UI to show the assigned agent and disables claiming.

### 4.2 Solution for INC-0304 (Absolute Private Note Data Isolation)
* **Vulnerability**: Internal team notes leaked to customer screen, API, or exports.
* **Fool-Proof Mitigation**:
  1. **Database & Service Layer Isolation**: The query retrieving messages for customer-facing views explicitly filters `WHERE is_private = false`.
  2. **Schema/DTO Separation**: Separate response models:
     - `CustomerTicketDetailView`: Serializes only `messages` where `is_private == false`.
     - `AgentTicketDetailView`: Serializes both, with explicit `is_private: true` field.
  3. **UI Visual Distinction**:
     - Agent interface has two distinct inputs: "Reply to Customer" (Blue/White, labeled "Sends email/reply to customer") and "Internal Note" (Yellow/Amber, labeled "Visible only to internal team members, never shown to customer").
     - Private notes rendered inside a high-contrast amber box with a prominent lock icon `🔒 Internal Note`.

### 4.3 Solution for INC-0318 (Non-Repudiation Immutable Audit Trail)
* **Vulnerability**: Disputed reply times and missing proof of actions.
* **Fool-Proof Mitigation**:
  1. Every action (claiming ticket, posting reply, adding note, status transition, priority change) writes synchronously to `audit_logs` in the same database transaction.
  2. Database grants: In production, the DB user used by the app has no `UPDATE` or `DELETE` privilege on `audit_logs` (read and insert only).
  3. UI includes a dedicated "Audit History" timeline tab showing exact timestamps, actor name, action, and payload.

---

## 5. Working Hours & SLA Engine Specification

### 5.1 Business Hours Parameters
* **Start Time**: `09:30:00`
* **End Time**: `18:30:00` (9 working hours per day = 540 working minutes)
* **Working Days**: Monday through Friday
* **Non-Working Days**: Saturday, Sunday, and dates defined in `holidays` table

### 5.2 Priority SLAs

| Priority | First Response SLA | Resolution SLA |
|---|---|---|
| **Urgent** (`cannot work at all`) | 2 business hours (120 min) | Same working day (End of current business day at 18:30, or within 9 business hours) |
| **Medium** | Half working day (4.5 business hours = 270 min) | 3 working days (27 business hours) |
| **Small** (`questions/requests`) | 1 working day (9 business hours = 540 min) | 1 working week (5 working days = 45 business hours) |

### 5.3 Business Hours Calculation Algorithm
To compute deadline:
1. Start at `start_datetime`. If `start_datetime` is outside business hours, advance to the next `09:30` on a valid business day.
2. Add remaining target minutes sequentially within the `09:30 - 18:30` window.
3. If end of current business day (`18:30`) is reached, carry remainder to `09:30` of the next non-weekend, non-holiday day.
4. When ticket moves to `waiting_on_customer`, record `sla_paused_at`.
5. When customer replies, calculate business minutes elapsed between `sla_paused_at` and current time, and advance `first_response_due_at` and `resolution_due_at` by that duration.

### 5.4 Resolution to the Unanswered Meeting Question (Mid-lifecycle Priority Escalation)
* **Document Question**: *"What happens to the timer if we change a ticket to urgent in the middle?"*
* **Design Decision & Rationale**:
  - If a ticket is escalated to `urgent`:
    1. If first response has not yet occurred: The remaining response SLA is clamped to `min(remaining_time, 2_business_hours)`.
    2. Resolution SLA is immediately reset to the end of the current working day (18:30), or 2 hours if less than 2 hours remain in the working day.
    3. An immutable audit log entry is recorded noting `PRIORITY_ESCALATED` with previous and new SLA deadlines.

### 5.5 Auto-Close and Reopening Rules
* **Auto-Close**: A background task / evaluator checks tickets in `waiting_on_customer` status. If customer has not responded for 5 working days (45 business hours), status transitions to `closed` with system note and audit log.
* **Reopen Policy**:
  - If status is `done`, customer can reopen within 7 calendar days.
  - If customer attempts to reopen after 7 days, backend rejects reopen request and instructs creating a new ticket.

---

## 6. Support Agent Single-Screen UI Layout

```
+----------------------------------------------------------------------------------------------------+
|  FRONTDESK SUPPORT PORTAL  (Logged in as: Meera | Support Lead)               [Filter: All/Mine]   |
+----------------------------------------------------------------------------------------------------+
|  LEFT PANEL: TICKET QUEUE (Auto-sorted by SLA urgency) | RIGHT PANEL: ACTIVE TICKET WORKSPACE      |
|                                                        |                                           |
|  [Filter Tabs: All | My Tickets | Overdue | Waiting]   | INC-0319: "Cannot login to production"     |
|                                                        | Priority: [URGENT]  Status: [IN PROGRESS] |
|  ---------------------------------------------------   | Assigned to: Meera  | SLA: Due in 42 mins |
|  [!] INC-0319 - Urgent - System Down                   | ----------------------------------------- |
|      Due in: 42m | Customer: ACME Corp                 | TIMELINE & MESSAGES                       |
|                                                        | 10:00 Customer: "Our login is broken"     |
|  [W] INC-0312 - Medium - Invoice query                 | 10:15 [🔒 Internal Note] Meera:           |
|      Waiting on Customer (3 days)                      |       "Checked auth DB, restarting pod"   |
|                                                        | ----------------------------------------- |
|  [✓] INC-0298 - Small - How to export data             | ACTION AREA:                              |
|      Resolved | Claimed by: Alex                       | (o) Reply to Customer   ( ) Internal Note |
|                                                        | +---------------------------------------+ |
|  [+] Button: "Take this ticket" (Atomic claim)         | | Type message here...                  | |
|                                                        | +---------------------------------------+ |
|                                                        | [ Send Customer Reply ]  [ Mark Done ]    |
+----------------------------------------------------------------------------------------------------+
```

---

## 7. Step-by-Step Implementation Roadmap

### Phase 1: Workspace & Data Layer Setup
1. Initialize FastAPI backend structure with SQLAlchemy & Pydantic.
2. Configure SQLite (local development) and PostgreSQL compatibility (production).
3. Create database models: `Agent`, `Ticket`, `Message`, `AuditLog`, `Holiday`.
4. Seed default test data: 9 agents (including Meera), sample festival holidays, initial tickets representing realistic problems.

### Phase 2: Business Hours SLA Calculator
1. Implement pure calendar/clock utility:
   - `is_business_time(dt)`
   - `add_business_time(dt, duration)`
   - `calculate_business_time_elapsed(start_dt, end_dt)`
2. Unit test edge cases:
   - Ticket arriving Friday 18:00 (due time rolls into Monday morning).
   - Ticket created right before a festival holiday.
   - SLA pause duration subtraction when status is `waiting_on_customer`.
   - Priority escalation SLA recalculation.

### Phase 3: Backend REST APIs & Security Rules
1. **Ticket Operations**:
   - `GET /api/tickets`: List tickets with computed SLA status (`overdue`, `due_soon`, `healthy`, `waiting`).
   - `POST /api/tickets`: Create new ticket.
   - `POST /api/tickets/{id}/claim`: Atomic claim using DB-level lock (verifies INC-0291).
   - `POST /api/tickets/{id}/messages`: Post public reply or private team note (INC-0304).
   - `POST /api/tickets/{id}/status`: Transition status (`waiting_on_customer`, `done`, `closed`, `reopened`).
2. **Audit Logging Service**: Every state modification triggers synchronous append to `audit_logs` (INC-0318).
3. **Customer vs Agent Serialization**: Strict DTOs ensuring customer views never contain `is_private=true` records.

### Phase 4: Single-Screen Agent Frontend
1. Build single-screen responsive interface with React + Vite.
2. Queue list with visual badges:
   - Red: Overdue
   - Orange: Due within 1 hour
   - Blue: Waiting on customer
   - Gray: Done / Closed
3. Ticket Detail view with:
   - Prominent "Take this ticket" button that disables instantly upon successful claim or conflict.
   - Dual-mode editor: "Public Customer Reply" (Blue theme) vs "Private Team Note" (High-visibility amber theme with lock badge).
   - Live Audit Trail tab showing exact chronological history.

### Phase 5: Verification & Quality Assurance
1. **Concurrency test**: Simulate 2 concurrent requests claiming the same ticket; ensure 1 succeeds and 1 gets HTTP 409.
2. **Data leakage test**: Call ticket endpoint without agent auth or simulate export; verify 0 private notes are returned.
3. **Weekend SLA test**: Create ticket at Friday 18:00, verify SLA deadline is Monday morning, not Saturday or Sunday.
4. **Auto-close & Reopen test**: Verify reopening after 7 days is rejected.

### Phase 6: Packaging & Deployment
1. Create `Dockerfile` or Render/Railway configuration for zero-setup cloud deployment.
2. Write comprehensive `README.md` with:
   - Architecture overview
   - Local setup instructions (`npm run dev`, `uvicorn main:app`)
   - Edge case explanations
   - Section answering the mandatory test question: *"What did you not finish, and why?"*
