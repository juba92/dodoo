"""Covering-index DDL helper (`account`'s first — mirrors `hr`/`stock`'s
`ensure_indexes(env, ddl)` convention). PERF-001/002/004."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

_log = logging.getLogger(__name__)

# PERF-001: Trial Balance / General Ledger opening-balance queries filter
# account_move_line by (account_id, date) for both the in-period and the
# pre-date_from aggregate.
# PERF-002: reconciliation match-suggestion (suggest_matches) only ever scans
# a partner's still-open payment_term lines — a partial index on the open
# subset keeps the scan small regardless of how large the ledger grows.
# PERF-004: currency-rate lookup ("rate as of date") queries
# `WHERE currency_id = :cid AND rate_date <= :date ORDER BY rate_date DESC
# LIMIT 1` — an index matching that exact order lets it satisfy the query
# with an index-only scan instead of a sort.
PERF_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_account_move_line_account_date "
    "ON account_move_line (account_id, date)",
    "CREATE INDEX IF NOT EXISTS idx_account_move_line_partner_open "
    "ON account_move_line (partner_id, reconciled) WHERE reconciled = FALSE",
    "CREATE INDEX IF NOT EXISTS idx_res_currency_rate_currency_date "
    "ON res_currency_rate (currency_id, rate_date DESC)",
]


async def ensure_indexes(env: Any, ddl: list[str]) -> None:
    async with env.dml_conn() as conn:
        for stmt in ddl:
            try:
                await conn.execute(text(stmt))
            except Exception:  # noqa: BLE001 — an index race / pre-existing variant must not abort install
                _log.debug("index skipped: %s", stmt, exc_info=True)
        await conn.commit()
