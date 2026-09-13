from __future__ import annotations

import logging

from dodoo.addons.analytic.data.ir_model_sync import sync_ir_model

_log = logging.getLogger(__name__)

_MODELS = [
    ("analytic.plan", "analytic_plan"),
    ("analytic.account", "analytic_account"),
]


async def seed_analytic_data(env) -> None:
    await sync_ir_model(env, _MODELS)
    _log.info("Registered analytic.plan / analytic.account in ir_model")
