"""``stock.move`` — a planned movement of a product/quantity between two locations (ADR-030).

``action_set_state`` is the single "a move becomes done" choke point every workflow (transfer
validation, count application, scrap confirmation) routes through, and the one function
``stock_account`` hooks at import time (ADR-034/D6) without ``stock`` ever knowing it exists.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from dodoo.addons.stock._audit import log_conflict, log_transition
from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Char, Float, Many2one, Selection
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

STATE_CHOICES = [
    ("draft", "Draft"),
    ("waiting", "Waiting"),
    ("confirmed", "Confirmed"),
    ("ready", "Ready"),
    ("done", "Done"),
    ("cancelled", "Cancelled"),
]

# Legal manual transitions (ADR-030). "draft" -> "done" directly is for standalone,
# immediate moves that skip reservation entirely (scrap, inventory-adjustment) — the
# picking-driven flow always passes through action_reserve first regardless.
_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"waiting", "confirmed", "ready", "done", "cancelled"},
    "waiting": {"waiting", "confirmed", "ready", "done", "cancelled"},
    "confirmed": {"waiting", "confirmed", "ready", "done", "cancelled"},
    "ready": {"waiting", "confirmed", "ready", "done", "cancelled"},
    "done": set(),
    "cancelled": set(),
}


class StockMove(BaseModel):
    _name = "stock.move"

    picking_id = Many2one("stock.picking")  # null for standalone moves (scrap, count adjustment)
    product_id = Many2one("product.product", required=True)
    product_uom_qty = Float(required=True)
    product_uom_id = Many2one("uom.uom")  # optional for standalone moves (scrap, adjustment)
    location_src_id = Many2one("stock.location", required=True)
    location_dest_id = Many2one("stock.location", required=True)
    state = Selection(STATE_CHOICES, default="draft")
    origin = Char(size=256)

    # ------------------------------------------------------------------ reservation

    @classmethod
    async def action_reserve(cls, env: Environment, move_id: int, uid: int | None = None) -> str:
        """Attempt to reserve ``product_uom_qty`` from the source location (D2); returns the
        resulting state (waiting/confirmed/ready). A non-internal source (Vendors, Customers,
        Transit, …) is treated as an unlimited supply — only `internal` locations carry a
        finite on-hand quantity to reserve against (FR-016)."""
        from dodoo.addons.stock.models.stock_location import StockLocation
        from dodoo.addons.stock.models.stock_quant import StockQuant

        rows = await super().read(
            env, [move_id], ["product_id", "product_uom_qty", "location_src_id", "state"]
        )
        if not rows:
            raise DodooError("move_not_found")
        move = rows[0]
        if move["state"] in ("done", "cancelled"):
            return move["state"]

        src_usage = (
            await StockLocation.read(env, [move["location_src_id"]], ["usage"])
        )[0]["usage"]
        if src_usage != "internal":
            await cls.action_set_state(env, [move_id], "ready", uid=uid)
            return "ready"

        reserved = await StockQuant.reserve(
            env, move["product_id"], move["location_src_id"], move["product_uom_qty"]
        )
        if reserved <= 0:
            target = "waiting"
        elif reserved < move["product_uom_qty"]:
            target = "confirmed"
        else:
            target = "ready"
        await cls.action_set_state(env, [move_id], target, uid=uid)
        return target

    # ------------------------------------------------------------------ state

    @classmethod
    async def action_set_state(
        cls,
        env: Environment,
        ids: list[int],
        target: str,
        uid: int | None = None,
        expected_state: str | None = None,
    ) -> bool:
        if target not in dict(STATE_CHOICES):
            raise DodooError("move_transition_invalid")
        for mid in ids:
            rows = await super().read(env, [mid], ["state", "picking_id"])
            if not rows:
                raise DodooError("move_not_found")
            current = rows[0]["state"]
            if expected_state is not None and expected_state != current:
                log_conflict(
                    _log,
                    model=cls._name,
                    record_id=mid,
                    event="move_state_conflict",
                    expected=expected_state,
                    actual=current,
                    actor_uid=uid,
                )
                raise DodooError("move_state_conflict")
            if target == current:
                continue
            if target not in _TRANSITIONS.get(current, set()):
                raise DodooError("move_transition_invalid")
            await super().write(env, [mid], {"state": target})
            log_transition(
                _log,
                model=cls._name,
                record_id=mid,
                event="move_state",
                frm=current,
                to=target,
                actor_uid=uid,
            )
        return True
