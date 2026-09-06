"""``fleet.vehicle`` — a fleet asset with a seven-state lifecycle (ADR-027, FR-052…FR-054)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.addons.hr._audit import log_conflict, log_transition
from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Boolean, Char, Float, Json, Many2one, Selection
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

STATE = [
    ("new_request", "New Request"),
    ("to_order", "To Order"),
    ("ordered", "Ordered"),
    ("registered", "Registered"),
    ("downgraded", "Downgraded"),
    ("reserved", "Reserved"),
    ("waiting_list", "Waiting List"),
]
_STATE_VALUES = {v for v, _ in STATE}


class FleetVehicle(BaseModel):
    _name = "fleet.vehicle"

    name = Char(size=128)
    model_id = Many2one("fleet.vehicle.model", required=True)
    brand_id = Many2one("fleet.vehicle.model.brand")
    license_plate = Char(size=32)
    company_id = Many2one("res.company", required=True)
    state = Selection(STATE, default="new_request")
    driver_id = Many2one("hr.employee")
    former_driver_ids = Json()
    needs_reassignment = Boolean(default=False)
    odometer = Float(default=0.0, readonly=True)

    # ------------------------------------------------------------------ create/write
    @classmethod
    async def _derive(cls, env: Environment, vals: dict[str, Any]) -> dict[str, Any]:
        if vals.get("model_id"):
            async with env.dml_conn() as conn:
                row = await conn.execute(
                    text("SELECT name, brand_id FROM fleet_vehicle_model WHERE id = :i"),
                    {"i": vals["model_id"]},
                )
                r = row.fetchone()
                if r:
                    vals.setdefault("brand_id", r[1])
                    brand = None
                    if r[1]:
                        b = await conn.execute(
                            text(
                                "SELECT name FROM fleet_vehicle_model_brand WHERE id = :i"
                            ),
                            {"i": r[1]},
                        )
                        br = b.fetchone()
                        brand = br[0] if br else None
                    plate = vals.get("license_plate") or ""
                    vals.setdefault(
                        "name", f"{brand or ''} {r[0]}".strip() + (f" / {plate}" if plate else "")
                    )
        return vals

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        return await super().create(env, await cls._derive(env, dict(vals)))

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        vals = dict(vals)
        if "model_id" in vals:
            vals = await cls._derive(env, vals)
        if "driver_id" in vals:
            for vid in ids:
                cur = await super().read(env, [vid], ["driver_id", "former_driver_ids"])
                prev = cur[0]["driver_id"] if cur else None
                if prev and prev != vals["driver_id"]:
                    hist = list(cur[0].get("former_driver_ids") or [])
                    if prev not in hist:
                        hist.append(prev)
                    await super().write(env, [vid], {"former_driver_ids": hist})
        return await super().write(env, ids, vals)

    # ------------------------------------------------------------------ state
    @classmethod
    async def action_set_state(
        cls,
        env: Environment,
        ids: list[int],
        target: str,
        uid: int | None = None,
        expected_state: str | None = None,
    ) -> dict[str, Any]:
        if target not in _STATE_VALUES:
            raise DodooError("vehicle_state_invalid")
        result: dict[str, Any] = {}
        for vid in ids:
            rows = await super().read(env, [vid], ["state", "company_id"])
            if not rows:
                raise DodooError("vehicle_not_found")
            current = rows[0]["state"]
            if expected_state is not None and expected_state != current:
                log_conflict(
                    _log,
                    model=cls._name,
                    record_id=vid,
                    event="vehicle_state_conflict",
                    expected=expected_state,
                    actual=current,
                    actor_uid=uid,
                )
                raise DodooError("vehicle_state_conflict")
            if target == current:
                continue
            await super().write(env, [vid], {"state": target})
            log_transition(
                _log,
                model=cls._name,
                record_id=vid,
                event="fleet_vehicle_state",
                frm=current,
                to=target,
                actor_uid=uid,
                company_id=rows[0]["company_id"],
            )
            result = {"id": vid, "state": target}
        return result

    @classmethod
    async def assign_driver(
        cls, env: Environment, vehicle_id: int, driver_id: int | None, uid: int | None = None
    ) -> dict[str, Any]:
        await cls.write(env, [vehicle_id], {"driver_id": driver_id, "needs_reassignment": False})
        log_transition(
            _log,
            model=cls._name,
            record_id=vehicle_id,
            event="fleet_driver_assign",
            to=str(driver_id) if driver_id else "none",
            actor_uid=uid,
        )
        return {"id": vehicle_id, "driver_id": driver_id}

    # ------------------------------------------------------------------ derived
    @classmethod
    async def read(
        cls, env: Environment, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        want_odo = fields is None or "odometer" in fields
        fetch = fields
        if want_odo and fields is not None and "id" not in fields:
            fetch = ["id", *fields]
        rows = await super().read(env, ids, fetch)
        if want_odo and rows:
            latest = await cls._latest_odometers(env, [r["id"] for r in rows])
            for r in rows:
                r["odometer"] = latest.get(r["id"], r.get("odometer") or 0.0)
        return rows

    @classmethod
    async def _latest_odometers(
        cls, env: Environment, ids: list[int]
    ) -> dict[int, float]:
        if not ids:
            return {}
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT DISTINCT ON (vehicle_id) vehicle_id, value "
                    "FROM fleet_vehicle_odometer WHERE vehicle_id = ANY(:ids) "
                    "ORDER BY vehicle_id, date DESC, id DESC"
                ),
                {"ids": ids},
            )
            return {r[0]: float(r[1]) for r in rows}

    @classmethod
    async def get_assigned(
        cls, env: Environment, employee_id: int
    ) -> list[dict[str, Any]]:
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT id, name, state FROM fleet_vehicle WHERE driver_id = :e "
                    "ORDER BY id"
                ),
                {"e": employee_id},
            )
            return [dict(r._mapping) for r in rows]

    @classmethod
    async def flag_reassignment_for_archived_drivers(
        cls, env: Environment
    ) -> dict[str, int]:
        async with env.dml_conn() as conn:
            result = await conn.execute(
                text(
                    "UPDATE fleet_vehicle v SET needs_reassignment = TRUE, write_date = now() "
                    "FROM hr_employee e "
                    "WHERE v.driver_id = e.id AND e.active = FALSE "
                    "AND v.needs_reassignment = FALSE RETURNING v.id"
                )
            )
            ids = [r[0] for r in result]
            await conn.commit()
        for vid in ids:
            log_transition(
                _log,
                model=cls._name,
                record_id=vid,
                event="fleet_needs_reassignment",
                to="flagged",
                actor_uid=None,
            )
        return {"flagged": len(ids)}
