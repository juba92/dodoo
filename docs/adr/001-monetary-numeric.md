# ADR-001: Use NUMERIC(20,6) for Monetary Columns

**Status**: Accepted | **Date**: 2026-06-07

## Context

Financial calculations require exact decimal arithmetic. IEEE 754 floating-point (FLOAT/DOUBLE) cannot represent 0.1 or 0.01 exactly, leading to rounding errors that accumulate across multi-line invoices and violate the double-entry balance constraint.

## Decision

All monetary columns (debit, credit, balance, amount_*, tax amounts) use `NUMERIC(20,6)` in PostgreSQL and Python `decimal.Decimal`. A new `Monetary` field type is added to `dodoo/core/fields.py`.

## Consequences

- Exact decimal arithmetic eliminates floating-point rounding bugs in accounting.
- `decimal.Decimal` arithmetic is slightly slower than float; acceptable at accounting scale.
- NUMERIC serializes to string in JSON — API consumers receive strings for monetary fields; they must parse with appropriate precision.
- Odoo uses FLOAT8 for monetary fields; this is a deliberate divergence for correctness.
