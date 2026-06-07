# ADR-004: Reports as Virtual Model Methods via execute_kw

**Status**: Accepted | **Date**: 2026-06-07

## Context

Financial reports (Trial Balance, General Ledger, P&L, Balance Sheet, Aged AR/AP) are read-only computed results. The existing web UI fetches all data via JSON-RPC `execute_kw`. Custom REST endpoints would require SPA JavaScript changes.

## Decision

Reports are implemented as virtual model classes (e.g. `AccountReportTrialBalance`) with `_name` set and no DB table. Each exposes a `get_report(**kwargs)` classmethod callable via `execute_kw`. The `search_read` method returns `[]` and `fields_get` returns report parameter fields.

## Consequences

- Zero web UI changes required — any `execute_kw` call to `get_report` works immediately.
- Report models cannot be browsed via the list view (they return no records) but their results can be displayed by adapting the generic list view with a custom renderer if needed.
- Custom REST endpoints were rejected because they require client-side routing changes.
- PostgreSQL views were rejected because they cannot accept date-range parameters without injection risk.
