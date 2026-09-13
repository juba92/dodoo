"""Inventory Accounting addon.

Reproduces the behaviour of the Odoo 19.0 `stock_account` addon: costing methods, stock
valuation layers, and journal posting into `account`. Depends on `stock` + `account`.

Wraps `StockMove.action_set_state` at Python import time (ADR-034/D6) so that every move driven
to "done" — by a transfer validation, a physical-inventory count, or a scrap confirmation, all of
which converge on this one choke point — also gets valued and posted, without `stock` ever
importing or referencing this addon. The wrap only exists in a deployment that actually imports
`dodoo.addons.stock_account`; `stock`'s own source carries no branch on whether that happened.
"""

import logging

from dodoo.addons.stock.models.stock_move import StockMove
from dodoo.addons.stock_account import http, models  # noqa: F401

_log = logging.getLogger(__name__)

_original_action_set_state = StockMove.action_set_state.__func__


async def _valuing_action_set_state(cls, env, ids, target, uid=None, expected_state=None):
    result = await _original_action_set_state(cls, env, ids, target, uid=uid, expected_state=expected_state)
    if target == "done":
        from dodoo.addons.stock_account.models.stock_valuation_layer import StockValuationLayer

        for move_id in ids:
            try:
                await StockValuationLayer.value_move(env, move_id, uid=uid)
            except Exception:  # noqa: BLE001 — valuation must never block the underlying move
                _log.exception("stock_account: value_move failed for move %s", move_id)
    return result


StockMove.action_set_state = classmethod(_valuing_action_set_state)


async def post_install(env):
    from dodoo.addons.stock_account.data.seed import seed_stock_account_data

    await seed_stock_account_data(env)
