"""``resource.calendar`` — a company's standard working week (feature 006, FR-021).

One calendar per company is seeded (Mon–Fri, 08:00–12:00 / 13:00–17:00). ``dayofweek``
follows the Odoo convention: ``'0'`` = Monday … ``'6'`` = Sunday. In SQL this maps to
``EXTRACT(ISODOW FROM d)::int - 1``.
"""

from __future__ import annotations

from dodoo.core.fields import Char, Float, Many2one, Selection
from dodoo.core.models import BaseModel

DAYOFWEEK = [
    ("0", "Monday"),
    ("1", "Tuesday"),
    ("2", "Wednesday"),
    ("3", "Thursday"),
    ("4", "Friday"),
    ("5", "Saturday"),
    ("6", "Sunday"),
]


class ResourceCalendar(BaseModel):
    _name = "resource.calendar"

    name = Char(size=64, required=True)
    company_id = Many2one("res.company", required=True)
    hours_per_day = Float(default=8.0)
    tz = Char(size=32, default="UTC")


class ResourceCalendarAttendance(BaseModel):
    _name = "resource.calendar.attendance"

    calendar_id = Many2one("resource.calendar", required=True)
    dayofweek = Selection(DAYOFWEEK, required=True)
    hour_from = Float(required=True)
    hour_to = Float(required=True)
