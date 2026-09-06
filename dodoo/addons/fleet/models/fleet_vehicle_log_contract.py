"""``fleet.vehicle.log.contract`` — leasing/insurance contract with expiry alert (ADR-027)."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Date, Many2one, Monetary, Selection, Text
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

FLEET_ALERT_WINDOW_DAYS = 30

COST_TYPE = [("leasing", "Leasing"), ("insurance", "Insurance")]
STATE = [("open", "Open"), ("expired", "Expired"), ("closed", "Closed")]


class FleetVehicleLogContract(BaseModel):
    _name = "fleet.vehicle.log.contract"

    vehicle_id = Many2one("fleet.vehicle", required=True)
    cost_type = Selection(COST_TYPE, required=True)
    amount = Monetary()
    currency_id = Many2one("res.currency")
    start_date = Date(required=True)
    expiration_date = Date(required=True)
    state = Selection(STATE, default="open")
    notes = Text()

    @staticmethod
    def _check(vals: dict[str, Any], current: dict[str, Any] | None = None) -> None:
        base = dict(current or {})
        base.update({k: v for k, v in vals.items() if v is not None})
        sd, ed = base.get("start_date"), base.get("expiration_date")
        if sd and ed and str(ed) < str(sd):
            raise DodooError("fleet_contract_dates")

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        cls._check(vals)
        return await super().create(env, vals)

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        if {"start_date", "expiration_date"} & set(vals):
            for cid in ids:
                cur = await super().read(env, [cid], ["start_date", "expiration_date"])
                cls._check(vals, cur[0] if cur else None)
        return await super().write(env, ids, vals)

    @classmethod
    async def get_expiry_alerts(
        cls, env: Environment, window_days: int | None = None
    ) -> list[dict[str, Any]]:
        window = FLEET_ALERT_WINDOW_DAYS if window_days is None else int(window_days)
        today = datetime.date.today()
        cutoff = today + datetime.timedelta(days=window)
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT c.id, c.vehicle_id, v.name, c.cost_type, c.expiration_date, "
                    "       c.state "
                    "FROM fleet_vehicle_log_contract c "
                    "JOIN fleet_vehicle v ON v.id = c.vehicle_id "
                    "WHERE c.state <> 'closed' "
                    "AND (c.expiration_date <= :cutoff OR c.state = 'expired') "
                    "ORDER BY c.expiration_date"
                ),
                {"cutoff": cutoff},
            )
            out: list[dict[str, Any]] = []
            for r in rows:
                exp = r[4]
                if isinstance(exp, str):
                    exp = datetime.date.fromisoformat(exp[:10])
                out.append(
                    {
                        "contract_id": r[0],
                        "vehicle_id": r[1],
                        "vehicle_name": r[2],
                        "cost_type": r[3],
                        "expiration_date": exp.isoformat(),
                        "days_left": (exp - today).days,
                    }
                )
        return out

    @classmethod
    async def run_fleet_contract_expiry(cls, env: Environment) -> dict[str, int]:
        async with env.dml_conn() as conn:
            result = await conn.execute(
                text(
                    "UPDATE fleet_vehicle_log_contract SET state = 'expired', write_date = now() "
                    "WHERE state = 'open' AND expiration_date < CURRENT_DATE RETURNING id"
                )
            )
            ids = [r[0] for r in result]
            await conn.commit()
        for cid in ids:
            _log.info(
                "hr.transition model=fleet.vehicle.log.contract event=contract_expiry "
                "record_id=%s from=open to=expired",
                cid,
            )
        return {"expired": len(ids)}
