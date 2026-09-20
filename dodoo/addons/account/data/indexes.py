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
# 009-customer-database PERF-002: get_ar_ledger's query filters `account_move`
# by (partner_id, move_type) — a table with no partner_id index at all before
# this feature — then joins to account_move_line's payment_term line per move.
# Confirmed by EXPLAIN ANALYZE against a real 5,000-line, 100k-row-table
# benchmark, iterating on the actual measured plan each time:
#   1. No partner_id index on account_move at all: full scan, ~13.7s.
#   2. + idx_account_move_partner_type (partner_id, move_type): the outer
#      account_move filter becomes an index scan, but the planner then
#      mis-estimates account_move_line's plain (move_id, display_type)
#      composite index as low-selectivity and instead scans
#      idx_account_move_line_display_type alone per outer row (payment_term
#      rows are ~1/6 of the whole table) — 20.5s, *worse*.
#   3. Replacing that composite index with a **partial** index scoped to
#      exactly this query's predicate (`WHERE display_type = 'payment_term'`)
#      gives the planner unambiguous selectivity — 19ms.
PERF_INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_account_move_line_account_date "
    "ON account_move_line (account_id, date)",
    "CREATE INDEX IF NOT EXISTS idx_account_move_line_partner_open "
    "ON account_move_line (partner_id, reconciled) WHERE reconciled = FALSE",
    "CREATE INDEX IF NOT EXISTS idx_res_currency_rate_currency_date "
    "ON res_currency_rate (currency_id, rate_date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_account_move_partner_type "
    "ON account_move (partner_id, move_type)",
    "CREATE INDEX IF NOT EXISTS idx_account_move_line_payment_term_move "
    "ON account_move_line (move_id) WHERE display_type = 'payment_term'",
]


async def ensure_indexes(env: Any, ddl: list[str]) -> None:
    async with env.dml_conn() as conn:
        for stmt in ddl:
            try:
                await conn.execute(text(stmt))
            except Exception:  # noqa: BLE001 — an index race / pre-existing variant must not abort install
                _log.debug("index skipped: %s", stmt, exc_info=True)
        await conn.commit()
