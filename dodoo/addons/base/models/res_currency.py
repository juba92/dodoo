from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

from dodoo.core.fields import Boolean, Char, Date, Integer, Many2one, Monetary
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


class ResCurrency(BaseModel):
    _name = "res.currency"

    code = Char(size=3, required=True)
    name = Char(size=64)
    symbol = Char(size=8)
    rounding = Integer(default=2)
    active = Boolean(default=True)


class ResCurrencyRate(BaseModel):
    """A currency's exchange rate as of a date (FR-023) — manual entry only.

    ``rate`` is company-currency units per 1 unit of ``currency_id`` (Odoo's convention).
    """

    _name = "res.currency.rate"

    currency_id = Many2one("res.currency", required=True)
    rate_date = Date(required=True)
    rate = Monetary(required=True)

    @classmethod
    async def get_rate(
        cls,
        env: Environment,
        currency_id: int,
        company_currency_id: int,
        date: datetime.date,
    ) -> float | None:
        """Latest rate for ``currency_id`` as of ``date`` (``rate_date <= date``).

        Returns ``None`` when ``currency_id == company_currency_id`` (no conversion needed)
        or when no rate has been entered yet.
        """
        if currency_id == company_currency_id:
            return 1.0
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT rate FROM res_currency_rate "
                    "WHERE currency_id = :cid AND rate_date <= :dt "
                    "ORDER BY rate_date DESC LIMIT 1"
                ),
                {"cid": currency_id, "dt": date},
            )
            r = row.fetchone()
            return float(r[0]) if r else None
