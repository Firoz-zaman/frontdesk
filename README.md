# Frontdesk — Helpdesk & SLA Operations System

[![Tests](https://img.shields.io/badge/tests-59%20passed-brightgreen.svg)]()
[![Backend](https://img.shields.io/badge/backend-FastAPI%200.115-blue.svg)]()
[![Frontend](https://img.shields.io/badge/frontend-React%2019%20%2B%20Vite-61dafb.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

> **Built for Arvo Systems** to replace shared spreadsheets and WhatsApp groups with a deterministic, real-time ticketing system featuring strict business-hour SLA calculations, atomic claim locks, immutable audit sourcing, and zero-leakage internal note isolation.

---

## 1. Quick Links & Live Deployments

| Component | Platform | URL |
|---|---|---|
| **Frontend Workspace** | Vercel | *Your Vercel Deployment URL* (e.g., `https://frontdesk-xxxx.vercel.app`) |
| **Backend API & SSE** | Render | `https://frontdesk-api-dxta.onrender.com` |
| **API Documentation** | Render / OpenAPI | `https://frontdesk-api-dxta.onrender.com/docs` |
| **Source Repository** | GitHub | `https://github.com/Firoz-zaman/frontdesk` |

---

## 2. Evaluation Credentials (Ready to Test)

The system is pre-seeded with all **9 Arvo support team members** and **real customer accounts**. You can log in using the credentials below, or click any **1-Click Profile Chip** on the sign-in screen:

### Shared Password for All Accounts
> **Password**: `arvo2026!`

### Accounts Matrix
| Persona | Name | Email | Role | What to Test |
|---|---|---|---|---|
| **Customer** | Rahul Sharma | `customer@acmecorp.com` | `customer` | Access dedicated Customer Portal, submit tickets, reply to support, verify internal notes are hidden. |
| **Customer** | Nisha Patel | `nisha@globaltech.in` | `customer` | Test multi-tenant customer isolation (cannot view Acme Corp tickets). |
| **Support Lead** | Meera | `meera@arvo.in` | `lead` | Full supervisory override, reassign tickets, resolve/reopen, view full audit logs. |
| **Support Agent** | Ravi | `ravi@arvo.in` | `agent` | Primary queue handler, claim tickets, post public replies & private notes. |
| **Support Agent** | Priya | `priya@arvo.in` | `agent` | Claim open tickets, collaborate on unassigned tickets. |
| **Support Agent** | Arjun | `arjun@arvo.in` | `agent` | Test 403 Forbidden RBAC (cannot modify tickets claimed by Ravi). |
| **Support Agent** | Sneha | `sneha@arvo.in` | `agent` | Active queue agent. |
| **Support Agent** | Vikram | `vikram@arvo.in` | `agent` | Active queue agent. |
| **Support Agent** | Ananya | `ananya@arvo.in` | `agent` | Active queue agent. |
| **Support Agent** | Rohan | `rohan@arvo.in` | `agent` | Active queue agent. |
| **Support Agent** | Deepa | `deepa@arvo.in` | `agent` | Active queue agent. |

---

## 3. How to Run Locally (Under 2 Minutes)

### Prerequisites
- Python 3.11+
- Node.js 18+ and `npm`

### Option 1: One-Click Startup Script (Recommended)
Clone the repository and run the root helper script:
```bash
git clone https://github.com/Firoz-zaman/frontdesk.git
cd frontdesk
chmod +x run.sh
./run.sh
```
This script automatically:
1. Provisions Python virtual environment `backend/venv` and installs dependencies.
2. Runs database migrations and seeds initial agents and tickets.
3. Installs frontend `npm` dependencies.
4. Starts the FastAPI backend on `http://localhost:8000`.
5. Starts the React Vite dev server on `http://localhost:5173`.

Visit **`http://localhost:5173`** in your browser.

---

### Option 2: Manual Step-by-Step

#### Backend Terminal:
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Frontend Terminal:
```bash
cd frontend
npm install
npm run dev
```

---

## 4. How the Arvo Problems Were Solved

### A. Problem INC-0291: Two Agents Claiming the Same Ticket
* **Problem**: Two agents opened the same spreadsheet row, clicked take, and sent conflicting replies within 60 seconds.
* **Frontdesk Solution**: Implemented **atomic claim locking** at both database and application level:
  - When an agent claims a ticket via `POST /api/tickets/{id}/claim`, the backend verifies `assigned_agent_id IS NULL`.
  - If already claimed by another agent, the API immediately rejects the second request with **HTTP 409 Conflict** (`"Ticket already claimed by <Agent Name>"`).
  - Simultaneously broadcasts a typed Server-Sent Event `TICKET_CLAIMED` across all active agent browsers, instantaneously disabling the claim button in real-time.

### B. Problem INC-0304: Private Team Note Leaked to Customer
* **Problem**: An internal note discussing a difficult customer was accidentally exposed to the customer.
* **Frontdesk Solution**: Engineered an airtight **Dual-Scope Note Isolation Wall**:
  - `Message` entity has a strict boolean flag `is_private`.
  - The customer endpoint `GET /api/customer/tickets/{id}/messages` executes an enforced SQL filter: `WHERE is_private = false`.
  - Private notes are stripped at the database query level, never loaded into memory for customer requests, never serialized in JSON responses, and never present in customer UI state. Verified by automated tests `test_e2e_05_note_isolation` and `test_cust_05_note_isolation_wall`.

### C. Problem INC-0318: Dispute Over Reply Times (Who is Right?)
* **Problem**: Customer claimed Arvo did not reply until morning; Arvo claimed 40 minutes. No proof existed.
* **Frontdesk Solution**: Implemented an **append-only, immutable Audit Trail**:
  - Every action (`TICKET_CREATED`, `TICKET_CLAIMED`, `PUBLIC_REPLY_SENT`, `CUSTOMER_REPLY_RECEIVED`, `PRIORITY_CHANGED`, `TICKET_RESOLVED`, `TICKET_REOPENED`) is written to an append-only `AuditLog` table with:
    - Precise ISO 8601 UTC timestamp.
    - Acting entity (`actor_type`, `actor_id`, `actor_name`).
    - Action type and structured payload diff.
  - The audit log has no `UPDATE` or `DELETE` endpoints, providing non-repudiation proof for SLA disputes.

### D. Meeting Requirement: Indian Business Hours SLA Engine
* **Business Hours**: 09:30 to 18:30 IST, Monday through Friday (9 working hours/day).
* **Weekend & Holiday Exclusion**: Timer stops at 18:30 Friday and resumes at 09:30 Monday. Excludes Indian national festival holidays (Republic Day, Independence Day, Gandhi Jayanti, Diwali, etc.).
* **Tier SLAs**:
  - **Urgent**: First response in 2 working hours; resolution same working day (by 18:30).
  - **Medium**: First response in 4.5 working hours (half day); resolution in 27 working hours (3 working days).
  - **Small**: First response in 9 working hours (1 day); resolution in 45 working hours (1 working week).
* **Waiting on Customer SLA Pause**:
  - When an agent posts a public reply, status transitions to `waiting_on_customer` and `sla_paused_at` records the timestamp.
  - The SLA clock completely freezes during this period ("That week is not our fault").
  - When the customer replies, the clock unfreezes, elapsed pause duration is added to deadlines, and status resumes to `in_progress`.
* **Mid-Stream Priority Changes**:
  - If a ticket changes priority mid-stream (e.g. Medium ➔ Urgent), the engine calculates consumed working hours and projects the new deadline from the initial created time adjusted for elapsed active hours.
* **Lifecycle Policies**:
  - **Auto-Close**: Tickets waiting on customer for 45 working hours (5 working days) automatically transition to `closed`.
  - **Reopen Window**: Resolved tickets can be reopened by customers within 5 working days (45 working hours). After that, the policy strictly requires a new ticket.

---

## 5. System Features & UX Highlights

1. **Agent Workspace (Unified Dashboard)**:
   - Real-time ticket queue with status and priority filter pills (`All`, `Urgent`, `Waiting on Customer`, `Breached`).
   - Active SLA breach badges showing countdown or hours overdue.
   - Dual-tab message composer: toggle effortlessly between **Public Reply** (sent to customer) and **Internal Note** (amber highlight, strictly team-only).
   - Reassign ticket modal (Lead only) and Priority escalation dropdown.
2. **Dedicated Customer Portal**:
   - Separate, branded client interface with zero access to agent endpoints.
   - Filter by `All`, `Action Required` (highlighting tickets waiting on them), `In Progress`, and `Resolved`.
   - Real-time response composer that immediately unpauses SLA timers and alerts agents.
3. **Real-Time Push Updates (Server-Sent Events)**:
   - Native SSE connection stream at `/api/events/stream`.
   - Live status beacon ("Live Connection Active" / "Connecting…") updating seamlessly.
   - Instant multi-tab synchronization without polling.
4. **System-Wide Dark Mode**:
   - One-click theme toggle (Sun/Moon icon) available on the Agent Navbar, Customer Portal Header, and Login screen.
   - Seamless high-contrast dark theme with persistent preference saved to `localStorage`.

---

## 6. Running the Automated Test Suite

The project includes **59 automated tests** covering unit logic, RBAC security, SLA mathematics, and end-to-end multi-persona workflows:

```bash
# Run all 59 tests in one command:
npm test && npm run test:e2e && npm run test:customer
```

### Breakdown of Test Suites:
1. **Core Unit & Policy Tests** (44 tests — `npm test`):
   - Business hours calculations, weekend jumps, festival holidays.
   - SLA deadline projections and mid-stream priority recalculations.
   - Auto-close policy and 5-day reopen eligibility window.
   - Senior engineer edge cases: concurrent claim race conditions, non-working hour ticket arrival.
2. **Production End-to-End Suite** (7 tests — `npm run test:e2e`):
   - Health check & version validation.
   - Agent login gateway & JWT rejection.
   - Ticket ownership RBAC (Arjun blocked from Ravi's ticket).
   - Strict note isolation verification.
   - SSE stream handshake.
3. **Multi-Persona Customer Portal Suite** (8 tests — `npm run test:customer`):
   - Customer authentication & profile retrieval (`Rahul Sharma`).
   - Cross-customer data isolation (Customer A blocked from Customer B).
   - Zero-leakage note wall.
   - Full end-to-end SLA pause/resume cycle.
   - Role-based boundary enforcement (Customer credentials strictly blocked from agent endpoints).
   - Customer SSE live stream connection verification.

---

## 7. Architecture & Tech Stack

```
project-11/
├── backend/
│   ├── app/
│   │   ├── api/v1/         # Versioned REST routers (tickets, messages, customer, events)
│   │   ├── core/           # Security (Argon2id, JWT), dependencies, config
│   │   ├── events.py       # Async broadcaster for Server-Sent Events (SSE)
│   │   ├── lifecycle.py    # Auto-close & reopen policy evaluation
│   │   ├── models.py       # SQLAlchemy ORM models (Ticket, Message, Agent, Customer, AuditLog)
│   │   ├── seed.py         # 9 Arvo agents + 2 enterprise customer accounts
│   │   ├── sla.py          # Deterministic Indian business hours SLA engine
│   │   └── utils.py        # Safe ticket ID generation (INC-XXXX)
│   └── tests/              # 59 automated test cases
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── auth/       # Login gateway with 1-click profiles
│   │   │   ├── common/     # ThemeToggle, StatusPill, Badge, Button, Modal
│   │   │   ├── customer/   # Dedicated Customer Portal & Ticket Composer
│   │   │   ├── layout/     # DashboardLayout, Navbar
│   │   │   └── tickets/    # TicketQueue, TicketDetail, MessageList, Composer
│   │   ├── context/        # AuthContext, ThemeContext
│   │   └── styles/         # Design tokens, dark mode overrides, auth CSS
│   └── vercel.json         # Vercel SPA deployment rules
├── render.yaml             # Render Blueprint specification
└── DEPLOYMENT.md           # Step-by-step free cloud hosting guide
```
