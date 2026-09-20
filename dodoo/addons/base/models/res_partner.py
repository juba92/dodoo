from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Boolean, Char, Many2one
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment


class ResPartner(BaseModel):
    _name = "res.partner"

    name = Char(size=256, required=True)
    company_id = Many2one("res.company")
    email = Char(size=256)
    phone = Char(size=64)
    vat = Char(size=32)
    active = Boolean(default=True)
    is_company = Boolean(default=False)
    street = Char(size=256)
    city = Char(size=128)
    state_id = Many2one("res.country.state")
    zip = Char(size=32)
    country_id = Many2one("res.country")

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        """FR-001: ``name`` is required regardless of entry path (generic
        ``execute_kw`` or the dedicated ``/account/partner`` routes)."""
        if not vals.get("name"):
            raise DodooError("res.partner requires a non-empty 'name'")
        return await super().create(env, vals)

    @classmethod
    async def write(cls, env: Environment, ids: list[int], vals: dict[str, Any]) -> bool:
        if "name" in vals and not vals["name"]:
            raise DodooError("res.partner requires a non-empty 'name'")
        return await super().write(env, ids, vals)

    @classmethod
    async def unlink(cls, env: Environment, ids: list[int]) -> bool:
        """FR-006: a partner referenced by a posted invoice/credit-note/payment
        cannot be hard-deleted; archiving (``active=False``) remains available
        regardless. Mirrors ``AccountMove.unlink``'s posted-move guard shape.

        ``base`` has no dependency on ``account`` — ``account_move``/
        ``account_payment`` may not exist at all (a ``base``-only install), so
        each reference count is guarded with ``to_regclass`` and short-circuits
        to 0 rather than raising "relation does not exist".
        """
        async with env.dml_conn() as conn:
            for partner_id in ids:
                row = await conn.execute(
                    text(
                        "SELECT "
                        "(CASE WHEN to_regclass('account_move') IS NOT NULL "
                        " THEN (SELECT COUNT(*) FROM account_move WHERE partner_id = :pid) "
                        " ELSE 0 END) "
                        "+ (CASE WHEN to_regclass('account_payment') IS NOT NULL "
                        " THEN (SELECT COUNT(*) FROM account_payment WHERE partner_id = :pid) "
                        " ELSE 0 END) "
                        "AS ref_count"
                    ),
                    {"pid": partner_id},
                )
                ref_count = row.scalar_one() or 0
                if ref_count:
                    raise DodooError(
                        f"Partner {partner_id} has {ref_count} referencing invoice/payment "
                        "record(s) and cannot be deleted. Archive it instead."
                    )
        return await super().unlink(env, ids)
