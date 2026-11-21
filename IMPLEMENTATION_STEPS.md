# Frontdesk: Modular Step-by-Step Implementation Guide
## *Pluggable Architecture for High Resilience & Zero-Breakage Extensibility*

> **Guiding Principle**: Build an irreducible, fully operational **Core Base** first. Every subsequent feature is an isolated, loosely coupled module that plugs into the base via clean interfaces. If any module is omitted, disabled, or fails, the application continues to run without crashing or blocking core workflows.

---

## 1. Architectural Dependency Hierarchy

```
+-------------------------------------------------------------------------------+
|             LAYER 0: STABLE CORE BASE (Foundational & Self-Sufficient)        |
|  - FastAPI Backend & DB (SQLite / Postgres)                                   |
|  - Core Entities: Ticket & Agent                                              |
|  - Minimal CRUD APIs: List, Get Details, Create Ticket                        |
|  - Single-Screen Agent Split-View UI (Ticket Queue + Selected Ticket View)    |
+-------------------------------------------------------------------------------+
       |                     |                     |               |            
  [Plugs In]            [Plugs In]            [Plugs In]      [Plugs In]        
       v                     v                     v               v            
+--------------+     +---------------+     +--------------+  +---------------+  
|   MODULE 1   |     |   MODULE 2    |     |   MODULE 3   |  |   MODULE 4    |  
| Atomic Claim |     | Dual-Mode Msg |     |  Immutable   |  | Working Hours |  
|   Engine     |     |  & Isolation  |     | Audit Logger |  |  SLA Engine   |  
|  (INC-0291)  |     |  (INC-0304)   |     |  (INC-0318)  |  | (Meera's SLA) |  
+--------------+     +---------------+     +--------------+  +---------------+  
                                                                   |            
                                                              [Plugs In]        
                                                                   v            
                                                             +---------------+  
                                                             |   MODULE 5    |  
                                                             |   Lifecycle   |  
                                                             | Policies (7d) |  
                                                             +---------------+  
```

> [!IMPORTANT]
> **Dependency Isolation Rule**:
> - Feature modules communicate with the Base via clean service calls or event hooks.
> - No feature module directly imports or relies on private internals of another feature module.
> - E.g., The Audit Logger (Module 3) listens for state changes via a simple event emitter; if Audit Logging is disabled or throws an error, the ticket update still commits cleanly.

---

## Step 0: The Stable Core Base (The Kernel)

### Objective
Create a working, usable application on day one. At the end of Step 0, agents can already log in, view the list of tickets on a single screen, click a ticket to view details, and create new tickets.

### 0.1 Data Layer (Minimal Viable Schema)
Only the foundational tables with standard types:
- `agents`: `id`, `name`, `email`, `role`, `created_at`
- `tickets`: `id`, `title`, `description`, `customer_name`, `customer_email`, `priority` (`urgent`, `medium`, `small`), `status` (`open`, `in_progress`, `waiting_on_customer`, `done`, `closed`), `assigned_agent_id` (nullable), `created_at`

### 0.2 Base API Endpoints
- `GET /api/health` -> System health & DB connection check.
- `GET /api/agents` -> List agents (pre-seeded with Meera + 8 agents).
- `GET /api/tickets` -> List tickets (supports basic filters: all, status).
- `GET /api/tickets/{id}` -> Get single ticket details.
- `POST /api/tickets` -> Create new ticket.

### 0.3 Base UI: The Agent Single-Screen Workspace
- Responsive split-pane dashboard:
  - **Left Pane (40%)**: Scrollable list of tickets showing ticket ID, title, priority tag, status tag.
  - **Right Pane (60%)**: Selected ticket detail view (Title, Description, Customer info, Status).
- Agent selector dropdown in the navbar (e.g. "Logged in as Meera (Lead)").

> [!NOTE]
> **Step 0 Verification Checkpoint**:
> - Run backend (`uvicorn`) and frontend (`vite`).
> - The application is fully interactive: tickets can be browsed and created.
> - **Self-Sufficiency**: If you stopped here, you have an operational ticketing portal.

---

## Step 1: Pluggable Module 1 — Atomic Ticket Claiming (`INC-0291`)

### Why It's Pluggable
It only adds a single atomic status/assignment mutation. The base ticket list and details continue to work identically whether a ticket is claimed or unclaimed.

### 1.1 Backend Implementation
- Add endpoint: `POST /api/tickets/{id}/claim`
- Payload: `{ "agent_id": "uuid" }`
- **Atomic Concurrency Logic**:
  ```python
  # Atomic conditional update preventing race conditions
  result = db.execute(
      update(Ticket)
      .where(Ticket.id == ticket_id, Ticket.assigned_agent_id.is_(None))
      .values(assigned_agent_id=agent_id, status="in_progress")
  )
  if result.rowcount == 0:
      raise HTTPException(status_code=409, detail="Ticket already claimed by another agent")
  ```
- **Fallback / Resilience**: If concurrency check fails, returns HTTP 409 Conflict with current assignee details.

### 1.2 Frontend Integration
- In the right-pane detail view:
  - If `assigned_agent_id == null`, display prominent button: `[ Take This Ticket ]`.
  - When clicked: Calls `/claim`. If HTTP 409 is returned, an alert appears: *"Another agent claimed this ticket a moment ago."* and immediately re-fetches the ticket.
  - If already assigned, shows: `Assigned to: [Agent Name]`.

> [!NOTE]
> **Step 1 Verification Checkpoint**:
> - Open two browser tabs on the same unclaimed ticket.
> - Click "Take this ticket" on both simultaneously.
> - One succeeds and takes ownership; the other cleanly fails with 409 Conflict. Zero inconsistent state.

---

## Step 2: Pluggable Module 2 — Dual-Mode Messaging & Note Isolation (`INC-0304`)

### Why It's Pluggable
Messaging is an independent entity associated with `ticket_id`. Tickets exist without messages; adding messages does not mutate the base ticket structure.

### 2.1 Data Layer & Strict DTO Separation
- Table `messages`:
  - `id`: UUID (PK)
  - `ticket_id`: FK -> `tickets.id`
  - `sender_type`: `agent` | `customer` | `system`
  - `sender_name`: string
  - `content`: text
  - `is_private`: boolean (default `false`)
  - `created_at`: timestamp
- **Data Leakage Wall (DTO / Serializer Level)**:
  ```python
  # Customer View DTO excludes private messages unconditionally:
  def get_customer_messages(ticket_id: str, db: Session):
      return db.query(Message).filter(
          Message.ticket_id == ticket_id, 
          Message.is_private == False
      ).all()

  # Agent View DTO includes all messages with is_private flag:
  def get_agent_messages(ticket_id: str, db: Session):
      return db.query(Message).filter(Message.ticket_id == ticket_id).all()
  ```

### 2.2 Endpoints
- `GET /api/tickets/{id}/messages` (Supports query parameter `scope=agent` or `scope=customer`).
- `POST /api/tickets/{id}/messages` (Payload: `content`, `is_private`).

### 2.3 Frontend Integration
- Chat/Message Timeline in the right pane:
  - Public customer messages rendered with clean white/blue card style.
  - Private internal notes rendered with a high-contrast amber background, lock icon `🔒 Internal Team Note`, and text *"Never visible to customer"*.
- Message composer with a distinct tab or toggle switch:
  - **[ Public Reply to Customer ]** (Blue button: "Send Reply")
  - **[ 🔒 Private Team Note ]** (Amber button: "Save Internal Note")

> [!NOTE]
> **Step 2 Verification Checkpoint**:
> - Create an internal note.
> - Verify it appears in the agent timeline with the amber lock banner.
> - Call `GET /api/tickets/{id}/messages?scope=customer` or inspect public payload; verify private note is completely absent.

---

## Step 3: Pluggable Module 3 — Immutable Audit Event Sourcing (`INC-0318`)

### Why It's Pluggable
The audit trail is purely append-only and observational. It records what happened without imposing business rules on other modules.

### 3.1 Data Layer & Event Logger Service
- Table `audit_logs`:
  - `id`: BIGSERIAL (PK)
  - `ticket_id`: FK -> `tickets.id`
  - `actor_type`: `agent` | `customer` | `system`
  - `actor_name`: string
  - `action`: string (`CREATED`, `CLAIMED`, `PUBLIC_REPLIED`, `NOTE_ADDED`, `STATUS_CHANGED`, `PRIORITY_CHANGED`)
  - `metadata_json`: json
  - `created_at`: timestamp
- **Lightweight Event Hook**:
  ```python
  def log_audit_event(db: Session, ticket_id: str, actor_name: str, action: str, details: dict):
      try:
          event = AuditLog(
              ticket_id=ticket_id,
              actor_name=actor_name,
              action=action,
              metadata_json=details
          )
          db.add(event)
          db.commit()
      except Exception as e:
          # Failure to write audit does NOT crash the primary business operation
          logger.error(f"Audit log failure: {e}")
  ```

### 3.2 Endpoint & UI Integration
- Endpoint: `GET /api/tickets/{id}/audit` -> Returns timeline of all historical events.
- UI: Secondary tab in ticket workspace: **"Audit History"** showing timestamp, actor, action, and diff summary.

> [!NOTE]
> **Step 3 Verification Checkpoint**:
> - Perform any action (claim ticket, send message, change priority).
> - Audit tab shows exact timestamp and author.
> - There are zero API endpoints to update or delete audit logs.

---

## Step 4: Pluggable Module 4 — Working Hours SLA Engine

### Why It's Pluggable
The SLA engine is an analytical calculator. It takes a ticket's creation time, priority, and working hours calendar, and computes the deadline. If the SLA engine is removed or fails, the tickets still display normally; only the SLA countdown badge falls back to "Standard".

### 4.1 Pure Business Hours Calculator Service (`services/sla_engine.py`)
- Independent utility functions with no database coupling:
  - Working window: `09:30` to `18:30` (9 hours = 540 minutes / day).
  - Working days: Monday (0) to Friday (4).
  - Configurable holiday list (e.g., festival dates).
  - `add_business_minutes(start_dt, minutes_to_add) -> deadline_dt`
  - `calculate_business_minutes_between(start_dt, end_dt) -> elapsed_minutes`
- Priority Matrix:
  - **Urgent**: First reply = 120 mins; Resolution = End of current business day (18:30).
  - **Medium**: First reply = 270 mins (4.5 hours); Resolution = 3 business days (27 hours).
  - **Small**: First reply = 540 mins (1 day); Resolution = 5 business days (45 hours).

### 4.2 Pause on Customer Waiting
- When ticket status transitions to `waiting_on_customer`:
  - Record `sla_paused_at = now()`.
- When customer replies:
  - Calculate business minutes between `sla_paused_at` and `now()`.
  - Extend both `first_response_due_at` and `resolution_due_at` by that exact business interval.
  - Reset `sla_paused_at = None`.

### 4.3 Handling the Unanswered Meeting Question (Mid-Lifecycle Priority Escalation)
- Function: `recalculate_sla_on_priority_change(ticket, new_priority)`:
  - Recomputes resolution deadline to new priority limit from the escalation point.
  - Automatically logged to Module 3 Audit Trail.

### 4.4 UI Integration
- Queue list item displays a live SLA chip:
  - 🔴 **Overdue**: If past deadline.
  - 🟡 **Due in Xh Ym**: If within business hours.
  - 🔵 **Paused**: If status is `waiting_on_customer` ("Customer action required").

> [!NOTE]
> **Step 4 Verification Checkpoint**:
> - Create a ticket at Friday 18:00 with 2-hour SLA.
> - Deadline computes to Monday 10:30 (skipping 48 hours of weekend).
> - Mark ticket as "Waiting on Customer"; badge reflects "SLA Paused".

---

## Step 5: Pluggable Module 5 — Lifecycle Inactivity & Reopening Policies

### Why It's Pluggable
This is an automated policy layer. If omitted, agents can manually close and open tickets. When present, it enforces Arvo's business rules.

### 5.1 Auto-Close Inactive Tickets
- Policy rule: If ticket is in `waiting_on_customer` for $\ge$ 5 working days (45 working hours):
  - Service or scheduled evaluator transitions status to `closed`.
  - Generates system audit log: *"Auto-closed due to 1 week of customer inactivity."*

### 5.2 Reopening Policy Guard
- Policy rule: When `POST /api/tickets/{id}/reopen` is invoked:
  - If `now() - resolved_at > 7 calendar days`:
    - Reopen is rejected with HTTP 400: *"Tickets closed more than 1 week ago cannot be reopened. Please submit a new ticket."*
  - If within 7 calendar days:
    - Status transitions back to `in_progress`.

> [!NOTE]
> **Step 5 Verification Checkpoint**:
> - Test reopening a ticket resolved 2 days ago -> Allowed.
> - Test reopening a ticket resolved 8 days ago -> Blocked with instruction to create new ticket.

---

## Step 6: Testing, Packaging & Deployment

### 6.1 Automated Test Suite
- `test_base_crud.py`: Base ticket listing, detail, creation.
- `test_atomic_claiming.py`: Concurrent claiming race condition (INC-0291).
- `test_note_isolation.py`: Customer serializer omits `is_private=true` (INC-0304).
- `test_audit_logging.py`: Non-repudiation audit trail immutability (INC-0318).
- `test_sla_engine.py`: Weekend skip, festival holiday skip, pausing calculation.
- `test_reopen_policy.py`: Reopening 7-day boundary condition.

### 6.2 Deployment Package
- Single-command root runner / Docker setup.
- Database seeder script:
  - 9 support agents (Meera as support lead, 8 team agents).
  - Realistic initial tickets (demonstrating urgent, medium, small, overdue, waiting on customer).
  - Festival holidays pre-loaded for 2026.
- Production build deployed to free cloud host (Render / Railway / Fly.io / Vercel).

### 6.3 Submission Deliverables (Section 5 & 6)
1. **Live URL**: Accessible in browser.
2. **Repository Link**: Public GitHub/GitLab repo.
3. **README.md**: Architecture, quickstart guide, test instructions.
4. **The Short Note**: Clear, professional answer to: *"What did you not finish, and why?"*

---

## Summary of Resilience & Dependency Matrix

| Component | Can Function Without It? | Impact If Omitted or Disabled |
|---|---|---|
| **Layer 0: Core Base** | **No** (Foundational) | System cannot run. |
| **Module 1: Atomic Claiming** | **Yes** | Tickets can be assigned, but lacks race condition protection. |
| **Module 2: Note Isolation** | **Yes** | Basic ticket info works; no messaging/notes capability. |
| **Module 3: Audit Logger** | **Yes** | Actions proceed normally; history timeline is simply unpopulated. |
| **Module 4: SLA Engine** | **Yes** | Tickets function; SLA indicators show fallback status. |
| **Module 5: Lifecycle Policies** | **Yes** | Agents manually manage close/reopen without automated guards. |
