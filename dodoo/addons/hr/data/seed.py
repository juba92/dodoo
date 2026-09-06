"""``seed_hr_data`` — the HR addon's ``post_install`` entry point.

Order: ``ir_model`` rows (so ``ir.rule.model_id`` resolves) → groups → indexes → per-area
sample data → record rules. Every step is idempotent (count guards / ``ON CONFLICT``),
mirroring ``base_data.py`` / ``account_data.py``.

Per-area seed helpers and the model/index/rule lists are appended by the per-story data
modules as each user story is implemented; until then this seeds only the security scaffold.
"""

from __future__ import annotations

import logging
from typing import Any

from dodoo.addons.hr.data import groups, rules
from dodoo.addons.hr.data.indexes import ensure_indexes
from dodoo.addons.hr.data.ir_model_sync import sync_ir_model

_log = logging.getLogger(__name__)

# (model_name, table_name) pairs — extended per story via `IR_MODELS.extend(...)`.
IR_MODELS: list[tuple[str, str]] = []

# `CREATE INDEX IF NOT EXISTS …` statements — extended per story.
INDEXES: list[str] = []

# Callables `async (env) -> None` seeding one area's sample data — appended per story.
AREA_SEEDS: list[Any] = []


def _load_areas() -> None:
    """Import each area module for its ``IR_MODELS`` / ``INDEXES`` / ``HR_RULES`` side effects."""
    from dodoo.addons.hr.data import employees  # noqa: F401


async def seed_hr_data(env: Any) -> None:
    _load_areas()
    await sync_ir_model(env, IR_MODELS)
    await groups.seed(env)
    await ensure_indexes(env, INDEXES)
    for area_seed in AREA_SEEDS:
        await area_seed(env)
    await rules.apply(env)
    _log.info("hr: seed complete (%d models, %d indexes, %d areas)", len(IR_MODELS), len(INDEXES), len(AREA_SEEDS))
