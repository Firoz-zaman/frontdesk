"""Working Hours SLA Engine — Module 4 (Meera's Meeting Notes).

Rules defined strictly according to Arvo Systems specification:
- Working hours: 09:30 to 18:30 (9 hours = 540 minutes per working day)
- Working days: Monday through Friday
- Pauses on: Saturdays, Sundays, and Festival Holidays
- Urgent: First reply within 2 working hours (120 min), Fix same working day (18:30)
- Medium: First reply within half working day (4.5 hours = 270 min), Fix within 3 working days (27 hours)
- Small: First reply within 1 working day (9 hours = 540 min), Finish in about 1 working week (5 working days = 45 hours)
- Inactivity: SLA timer pauses when ticket moves to 'waiting_on_customer'
- Priority escalation: Recalculates remaining SLA from escalation time
"""
from datetime import datetime, date, time, timedelta, timezone
from typing import Optional, Any

# Business hours
WORK_START_HOUR = 9
WORK_START_MINUTE = 30
WORK_END_HOUR = 18
WORK_END_MINUTE = 30
WORK_MINUTES_PER_DAY = (WORK_END_HOUR * 60 + WORK_END_MINUTE) - (WORK_START_HOUR * 60 + WORK_START_MINUTE)  # 540 min

WORK_START_TIME = time(WORK_START_HOUR, WORK_START_MINUTE)
WORK_END_TIME = time(WORK_END_HOUR, WORK_END_MINUTE)

# Seed festival holidays for 2026 (YYYY-MM-DD)
DEFAULT_HOLIDAYS = {
    date(2026, 1, 26),  # Republic Day
    date(2026, 3, 4),   # Holi
    date(2026, 4, 3),   # Good Friday
    date(2026, 4, 14),  # Vishu / Tamil New Year
    date(2026, 5, 1),   # May Day
    date(2026, 8, 15),  # Independence Day
    date(2026, 8, 27),  # Onam
    date(2026, 10, 2),  # Gandhi Jayanti
    date(2026, 11, 8),  # Diwali
    date(2026, 12, 25), # Christmas
}


def _normalize_dt(dt: datetime) -> datetime:
    """Normalize datetime to timezone-aware UTC to prevent SQLite naive/aware comparison bugs."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_business_day(d: date, holidays: Optional[set[date]] = None) -> bool:
    """Check if date is Monday-Friday and not a festival holiday."""
    h_set = holidays if holidays is not None else DEFAULT_HOLIDAYS
    return d.weekday() < 5 and d not in h_set


def next_business_start(dt: datetime, holidays: Optional[set[date]] = None) -> datetime:
    """Find the next 09:30 on a valid working business day."""
    h_set = holidays if holidays is not None else DEFAULT_HOLIDAYS
    cur = dt
    # If currently on a business day before 09:30, start today at 09:30
    if is_business_day(cur.date(), h_set) and cur.time() < WORK_START_TIME:
        return cur.replace(hour=WORK_START_HOUR, minute=WORK_START_MINUTE, second=0, microsecond=0)

    # Otherwise advance day by day until we find a business day at 09:30
    cur_date = cur.date() + timedelta(days=1)
    while not is_business_day(cur_date, h_set):
        cur_date += timedelta(days=1)

    return datetime(
        cur_date.year, cur_date.month, cur_date.day,
        WORK_START_HOUR, WORK_START_MINUTE, 0, 0,
        tzinfo=dt.tzinfo or timezone.utc
    )


def add_business_minutes(start_dt: datetime, minutes_to_add: int, holidays: Optional[set[date]] = None) -> datetime:
    """Add business minutes according to 09:30-18:30 M-F working hours, skipping weekends & holidays."""
    start_dt = _normalize_dt(start_dt)
    if minutes_to_add <= 0:
        return start_dt

    h_set = holidays if holidays is not None else DEFAULT_HOLIDAYS
    cur = start_dt

    # If start_dt is outside business hours, advance to next business start
    if not is_business_day(cur.date(), h_set) or cur.time() < WORK_START_TIME or cur.time() >= WORK_END_TIME:
        cur = next_business_start(cur, h_set)

    remaining = minutes_to_add
    while remaining > 0:
        day_end = cur.replace(hour=WORK_END_HOUR, minute=WORK_END_MINUTE, second=0, microsecond=0)
        minutes_left_today = int((day_end - cur).total_seconds() // 60)

        if remaining <= minutes_left_today:
            return cur + timedelta(minutes=remaining)
        else:
            remaining -= minutes_left_today
            cur = next_business_start(cur, h_set)

    return cur


def calculate_business_minutes_between(start_dt: datetime, end_dt: datetime, holidays: Optional[set[date]] = None) -> int:
    """Calculate the number of business minutes elapsed between start_dt and end_dt."""
    start_dt = _normalize_dt(start_dt)
    end_dt = _normalize_dt(end_dt)
    if end_dt <= start_dt:
        return 0

    h_set = holidays if holidays is not None else DEFAULT_HOLIDAYS
    cur = start_dt
    total_minutes = 0

    if not is_business_day(cur.date(), h_set) or cur.time() < WORK_START_TIME or cur.time() >= WORK_END_TIME:
        cur = next_business_start(cur, h_set)
        if cur >= end_dt:
            return 0

    while cur < end_dt:
        day_end = cur.replace(hour=WORK_END_HOUR, minute=WORK_END_MINUTE, second=0, microsecond=0)
        chunk_end = min(end_dt, day_end)
        if chunk_end > cur and is_business_day(cur.date(), h_set) and cur.time() >= WORK_START_TIME:
            total_minutes += int((chunk_end - cur).total_seconds() // 60)

        cur = next_business_start(cur, h_set)

    return total_minutes


def compute_ticket_slas(created_at: datetime, priority: str, holidays: Optional[set[date]] = None) -> tuple[datetime, datetime]:
    """Compute first_response_due_at and resolution_due_at strictly by priority specification."""
    created_at = _normalize_dt(created_at)
    h_set = holidays if holidays is not None else DEFAULT_HOLIDAYS
    p = priority.lower()

    if p == "urgent":
        # First reply: 2 working hours = 120 minutes
        first_resp_due = add_business_minutes(created_at, 120, h_set)
        # Fix: same working day at 18:30 (or next working day 18:30 if created after 18:30 or non-business day)
        base = created_at
        if not is_business_day(base.date(), h_set) or base.time() >= WORK_END_TIME:
            base = next_business_start(base, h_set)
        resolution_due = base.replace(hour=WORK_END_HOUR, minute=WORK_END_MINUTE, second=0, microsecond=0)

    elif p == "medium":
        # First reply: half working day = 4.5 hours = 270 minutes
        first_resp_due = add_business_minutes(created_at, 270, h_set)
        # Fix: 3 working days = 3 * 540 = 1620 minutes
        resolution_due = add_business_minutes(created_at, 1620, h_set)

    else:  # small
        # First reply: 1 working day = 9 hours = 540 minutes
        first_resp_due = add_business_minutes(created_at, 540, h_set)
        # Fix: 1 working week = 5 working days = 5 * 540 = 2700 minutes
        resolution_due = add_business_minutes(created_at, 2700, h_set)

    return first_resp_due, resolution_due


def recalculate_sla_on_priority_change(
    current_time: datetime,
    new_priority: str,
    first_responded_at: Optional[datetime] = None,
    holidays: Optional[set[date]] = None,
) -> tuple[Optional[datetime], datetime]:
    """Resolves the unanswered meeting question:
    'What happens to the timer if we change a ticket to urgent in the middle?'

    Decision & Rationale:
    - If ticket has NOT received first response yet:
      Response deadline is reset to min(remaining_time, new_priority_response_time) from escalation.
    - Resolution deadline is immediately updated to the new priority duration from escalation.
    """
    current_time = _normalize_dt(current_time)
    if first_responded_at is not None:
        first_responded_at = _normalize_dt(first_responded_at)
    h_set = holidays if holidays is not None else DEFAULT_HOLIDAYS
    new_resp, new_res = compute_ticket_slas(current_time, new_priority, h_set)
    # If already responded to customer, response SLA is completed/frozen
    final_resp = None if first_responded_at is not None else new_resp
    return final_resp, new_res


def compute_sla_status(ticket: Any, current_time: Optional[datetime] = None) -> dict[str, Any]:
    """Evaluate ticket's real-time SLA health, returning status chips and labels."""
    now = current_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # If ticket is already resolved / closed
    if getattr(ticket, "status", None) in ("done", "closed"):
        return {
            "state": "completed",
            "badge_class": "sla-chip-completed",
            "label": "Resolved",
            "is_overdue": False,
            "is_paused": False,
        }

    # If ticket is waiting on customer (SLA PAUSED)
    if getattr(ticket, "status", None) == "waiting_on_customer" or getattr(ticket, "sla_paused_at", None) is not None:
        return {
            "state": "paused",
            "badge_class": "sla-chip-paused",
            "label": "⏸ SLA Paused (Waiting on Customer)",
            "is_overdue": False,
            "is_paused": True,
        }

    # Check deadlines
    res_due = getattr(ticket, "resolution_due_at", None)
    first_resp_due = getattr(ticket, "first_response_due_at", None)
    first_resp_done = getattr(ticket, "first_responded_at", None)

    # Determine primary active deadline: first response (if not done) or resolution
    active_deadline = first_resp_due if (first_resp_done is None and first_resp_due) else res_due

    if not active_deadline:
        return {
            "state": "healthy",
            "badge_class": "sla-chip-healthy",
            "label": "SLA Normal",
            "is_overdue": False,
            "is_paused": False,
        }

    if active_deadline.tzinfo is None:
        active_deadline = active_deadline.replace(tzinfo=timezone.utc)

    # Overdue check
    if now > active_deadline:
        overdue_min = int((now - active_deadline).total_seconds() // 60)
        hours, mins = divmod(overdue_min, 60)
        time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
        return {
            "state": "overdue",
            "badge_class": "sla-chip-overdue",
            "label": f"🚨 Overdue by {time_str}",
            "is_overdue": True,
            "is_paused": False,
            "overdue_minutes": overdue_min,
        }

    # Remaining time check
    remaining_min = int((active_deadline - now).total_seconds() // 60)
    hours, mins = divmod(remaining_min, 60)
    time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"

    if remaining_min <= 60:
        return {
            "state": "due_soon",
            "badge_class": "sla-chip-due-soon",
            "label": f"⏰ Due in {time_str}",
            "is_overdue": False,
            "is_paused": False,
            "remaining_minutes": remaining_min,
        }

    return {
        "state": "healthy",
        "badge_class": "sla-chip-healthy",
        "label": f"Due in {time_str}",
        "is_overdue": False,
        "is_paused": False,
        "remaining_minutes": remaining_min,
    }
