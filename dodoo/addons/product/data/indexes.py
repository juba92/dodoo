"""Covering-index DDL helper (pattern from ``account_data.py::_INDEXES``)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

_log = logging.getLogger(__name__)


async def ensure_indexes(env: Any, ddl: list[str]) -> None:
    async with env.dml_conn() as conn:
        for stmt in ddl:
            try:
                await conn.execute(text(stmt))
            except Exception:  # noqa: BLE001 — an index race / pre-existing variant must not abort install
                _log.debug("index skipped: %s", stmt, exc_info=True)
        await conn.commit()
