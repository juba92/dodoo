"""P2 area — Time Off (leave types, allocations, requests, calendars, public holidays)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from dodoo.addons.hr.data import rules, seed
from dodoo.addons.hr.security import GROUP_ADMIN, GROUP_EMPLOYEE, GROUP_OFFICER

_log = logging.getLogger(__name__)

_MODELS = [
    ("resource.calendar", "resource_calendar"),
    ("resource.calendar.attendance", "resource_calendar_attendance"),
    ("hr.public.holiday", "hr_public_holiday"),
    ("hr.leave.type", "hr_leave_type"),
    ("hr.leave.allocation", "hr_leave_allocation"),
    ("hr.leave", "hr_leave"),
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_hr_leave_employee_type_state "
    "ON hr_leave (employee_id, leave_type_id, state)",
    "CREATE INDEX IF NOT EXISTS idx_hr_leave_dates ON hr_leave (date_from, date_to)",
    "CREATE INDEX IF NOT EXISTS idx_hr_leave_company ON hr_leave (company_id)",
    "CREATE INDEX IF NOT EXISTS idx_hr_leave_allocation_employee_type "
    "ON hr_leave_allocation (employee_id, leave_type_id)",
    "CREATE INDEX IF NOT EXISTS idx_hr_public_holiday_range "
    "ON hr_public_holiday (date_from, date_to)",
    "CREATE INDEX IF NOT EXISTS idx_resource_calendar_attendance_cal "
    "ON resource_calendar_attendance (calendar_id, dayofweek)",
]

_RULES = [
    # hr.leave — owner OR their manager (Employee group); Officer/Administrator full.
    {
        "name": "hr.leave: own or team (Employee)",
        "model": "hr.leave",
        "domain": [
            "&",
            ["company_id", "in", "$company_ids"],
            "|",
            ["employee_id.user_id", "=", "$uid"],
            ["employee_id.manager_id.user_id", "=", "$uid"],
        ],
        "groups": [GROUP_EMPLOYEE],
        "perms": "rwc",
    },
    rules.officer_full("hr.leave"),
    rules.deny_all("hr.leave"),
    # hr.leave.allocation — same shape (read for owner/manager; Officer manages).
    {
        "name": "hr.leave.allocation: own or team (Employee)",
        "model": "hr.leave.allocation",
        "domain": [
            "|",
            ["employee_id.user_id", "=", "$uid"],
            ["employee_id.manager_id.user_id", "=", "$uid"],
        ],
        "groups": [GROUP_EMPLOYEE],
        "perms": "r",
    },
    rules.officer_full("hr.leave.allocation"),
    rules.deny_all("hr.leave.allocation"),
    # Config catalogs — read for all HR groups, write for Administrator.
    rules.catalog_read("hr.leave.type"),
    rules.catalog_admin_write("hr.leave.type"),
    rules.catalog_read("hr.public.holiday"),
    rules.catalog_admin_write("hr.public.holiday"),
    {
        "name": "resource.calendar: read (HR)",
        "model": "resource.calendar",
        "domain": [["company_id", "in", "$company_ids"]],
        "groups": [GROUP_EMPLOYEE, GROUP_OFFICER],
        "perms": "r",
    },
    {
        "name": "resource.calendar: write (Administrator)",
        "model": "resource.calendar",
        "domain": [[1, "=", 1]],
        "groups": [GROUP_ADMIN],
        "perms": "wck",
    },
    {
        "name": "resource.calendar.attendance: read (HR)",
        "model": "resource.calendar.attendance",
        "domain": [[1, "=", 1]],
        "groups": [GROUP_EMPLOYEE, GROUP_OFFICER],
        "perms": "r",
    },
    {
        "name": "resource.calendar.attendance: write (Administrator)",
        "model": "resource.calendar.attendance",
        "domain": [[1, "=", 1]],
        "groups": [GROUP_ADMIN],
        "perms": "wck",
    },
]

_LEAVE_TYPES = [
    ("Paid Time Off", "day", True, True, "manager"),
    ("Sick Time Off", "day", True, False, "hr"),
    ("Unpaid", "day", False, False, "manager"),
    ("Compensatory Days", "day", True, True, "manager"),
]

# Mon–Fri, 08:00–12:00 and 13:00–17:00 (dayofweek '0'..'4' = Mon..Fri).
_ATTENDANCE = [(str(d), h0, h1) for d in range(5) for (h0, h1) in ((8.0, 12.0), (13.0, 17.0))]


async def seed_timeoff_area(env: Any) -> None:
    async with env.dml_conn() as conn:
        companies = await conn.execute(text("SELECT id FROM res_company ORDER BY id"))
        company_ids = [r[0] for r in companies]

    from dodoo.addons.hr.models.hr_leave_type import HrLeaveType
    from dodoo.addons.hr.models.resource_calendar import (
        ResourceCalendar,
        ResourceCalendarAttendance,
    )

    for company_id in company_ids:
        async with env.dml_conn() as conn:
            has_cal = await conn.execute(
                text("SELECT 1 FROM resource_calendar WHERE company_id = :c LIMIT 1"),
                {"c": company_id},
            )
            if has_cal.fetchone():
                continue
        cal_id = await ResourceCalendar.create(
            env, {"name": "Standard 40h/week", "company_id": company_id, "hours_per_day": 8.0}
        )
        for dow, h0, h1 in _ATTENDANCE:
            await ResourceCalendarAttendance.create(
                env,
                {"calendar_id": cal_id, "dayofweek": dow, "hour_from": h0, "hour_to": h1},
            )

    async with env.dml_conn() as conn:
        has_types = await conn.execute(text("SELECT 1 FROM hr_leave_type LIMIT 1"))
        if has_types.fetchone():
            _log.info("hr: leave types already seeded; skipping")
            return
    for name, unit, paid, alloc_req, mode in _LEAVE_TYPES:
        await HrLeaveType.create(
            env,
            {
                "name": name,
                "request_unit": unit,
                "is_paid": paid,
                "allocation_required": alloc_req,
                "approval_mode": mode,
            },
        )
    _log.info("hr: seeded P2 time-off data (calendars, leave types)")


seed.IR_MODELS.extend(_MODELS)
seed.INDEXES.extend(_INDEXES)
seed.AREA_SEEDS.append(seed_timeoff_area)
rules.HR_RULES.extend(_RULES)
