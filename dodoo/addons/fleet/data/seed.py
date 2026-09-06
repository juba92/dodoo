"""``seed_fleet_data`` — the Fleet addon's ``post_install`` entry point.

Same shape as ``hr.data.seed``: ``ir_model`` rows → Fleet Manager group → indexes → sample
brands/models → record rules. Idempotent. Per-area lists are filled by the fleet model modules
as US6 is implemented.
"""

from __future__ import annotations

import logging
from typing import Any

from dodoo.addons.fleet.data import groups, rules
from dodoo.addons.fleet.data.indexes import ensure_indexes
from dodoo.addons.fleet.data.ir_model_sync import sync_ir_model

_log = logging.getLogger(__name__)

IR_MODELS: list[tuple[str, str]] = []
INDEXES: list[str] = []
AREA_SEEDS: list[Any] = []


def _load_areas() -> None:
    from dodoo.addons.fleet.data import vehicles  # noqa: F401


async def seed_fleet_data(env: Any) -> None:
    _load_areas()
    await sync_ir_model(env, IR_MODELS)
    await groups.seed(env)
    await ensure_indexes(env, INDEXES)
    for area_seed in AREA_SEEDS:
        await area_seed(env)
    await rules.apply(env)
    _log.info("fleet: seed complete (%d models, %d indexes)", len(IR_MODELS), len(INDEXES))
