# FRONTDESK FIX_V2 — SENIOR ENGINEERING AUDIT & RESOLUTION PLAN

> **Author**: Senior Systems & Platform Engineer  
> **Status**: In Progress / Active Execution  
> **Baseline Commit**: `fe20d98` (Frontdesk v3.0 Production Modularization)  
> **Target Repository**: `git@github.com:Firoz-zaman/frontdesk.git` (`main`)

---

## 1. Executive Summary & Senior Engineering Philosophy

Frontdesk v3 successfully modularized our FastAPI backend into clean domain routers (`core/`, `api/v1/`), isolated stateful UI components, introduced Argon2id authentication, and verified a 65-test regression suite.

However, a senior engineering audit reveals several **latent production reliability hazards**, subtle concurrency bugs, and architectural misalignments that pass superficial tests but degrade or fail under real-world multi-user production load:

1. **Silent Event Loss across the Sync/Async Worker Thread Boundary**:
   FastAPI synchronous route handlers (`claim`, `message`, `resolve`) run in AnyIO worker threads where `asyncio.get_event_loop()` raises a `RuntimeError`. The exception was swallowed by `except Exception: pass`, completely silencing real-time SSE broadcasts.
2. **Database Write Concurrency Locks in Multi-Agent Workflows**:
   SQLite's default `DELETE` journal mode and `busy_timeout = 0` cause `sqlite3.OperationalError: database is locked` when multiple agents concurrently claim tickets, post messages, or run SLA checks.
3. **CORS Security Specification Violation (Wildcard with Credentials)**:
   `CORSMiddleware` configured with `allow_origins=["*"]` and `allow_credentials=True` violates the W3C CORS specification and causes browser network rejections for authenticated credentials.
4. **SSE EventSource Infinite Reconnection Loop & Session Staling**:
   The frontend `useEventStream` hook mounts once with an initial token. On JWT expiry or 401 Unauthorized responses, native `EventSource` enters an unthrottled reconnect loop hammering `/api/events/stream`.
5. **Timestamp Sub-Minute Precision & Timezone Offset Resilience**:
   Sub-minute customer replies and naive vs UTC comparisons in SLA pause calculations risk zero-minute drops and state inconsistencies during high-frequency ticket updates.

---

## 2. Exhaustive Senior Engineering Audit Matrix

| Issue ID | Subsystem | Severity | Symptom / Failure Mode | Root Cause Analysis | Senior Engineering Solution |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **FIX-01** | `events.py` / `api/v1/tickets.py` | **Critical** | Zero SSE broadcasts received by clients during ticket claims, messages, or resolves. | Sync FastAPI endpoints run in AnyIO worker threads. Calling `asyncio.get_event_loop()` raises `RuntimeError`, swallowed silently. | Introduce `broadcaster.set_loop()` in app lifespan. Implement thread-safe `broadcaster.publish()` using `loop.call_soon_threadsafe()`. |
| **FIX-02** | `database.py` | **High** | Multi-agent concurrency throws `OperationalError: database is locked`. | SQLite defaults to rollback journal (`DELETE`) with default busy timeout. Concurrent writes conflict. | Enable SQLite Write-Ahead Logging (`WAL`) mode, `busy_timeout=5000` ms, and `synchronous=NORMAL` via SQLAlchemy engine connect hook. |
| **FIX-03** | `config.py` / `main.py` | **High** | Authenticated browser requests fail or are blocked by browser CORS policy. | `allow_origins=["*"]` is strictly illegal under W3C CORS spec when `allow_credentials=True`. | Define explicit allowed origins (`localhost:5173`, `127.0.0.1:5173`, configurable via env) for credentials. |
| **FIX-04** | `useEventStream.js` | **Medium** | Reconnect storms hammering server on 401; stream not updating on agent login/switch. | `EventSource` has no exponential backoff; hook runs on mount with static token from initial render. | Add reactive token tracking, reconnect backoff, and clean disconnection on unauthenticated / terminal errors. |
| **FIX-05** | `messages.py` / `sla.py` | **Medium** | Sub-minute SLA pause drops during rapid customer-agent exchanges. | SLA paused minutes calculation rounded to integer minute without fractional tracking or monotonic check. | Ensure UTC normalization and monotonic time calculations for ticket resumption and audit logs. |

---

## 3. Systematic Execution & Commit Strategy

Following the senior engineer mandate (**find problems -> fix -> test -> commit -> push -> repeat**):

- [x] **Audit & Documentation**: Author `FIX_V2.md` defining the exact problem matrix.
- [ ] **Fix 1 (`fix(events)`)**: Implement thread-safe SSE broadcaster & unskip integration test.
- [ ] **Fix 2 (`fix(database)`)**: Enable SQLite WAL mode and 5-second busy timeout for safe concurrent writes.
- [ ] **Fix 3 (`fix(security)`)**: Enforce explicit CORS origins for credentialed sessions.
- [ ] **Fix 4 (`fix(frontend)`)**: Enhance frontend SSE stream hook with reactive token & backoff.
- [ ] **Fix 5 (`fix(sla)`)**: Harden SLA calculation precision and timestamp consistency.
- [ ] **Verification**: Execute full regression test suites (100% pass guarantee).
