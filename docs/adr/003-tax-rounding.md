# ADR-003: round_globally Tax Computation

**Status**: Accepted | **Date**: 2026-06-07

## Context

When computing tax amounts on multi-line invoices, two strategies exist: round each line's tax individually (round_per_line) or sum all raw tax amounts then round once (round_globally).

## Decision

Use `round_globally`: accumulate raw tax amounts across all product lines per tax, then round the total once to `currency.rounding` decimal places.

## Consequences

- Eliminates the "sum of rounded parts ≠ rounded whole" penny imbalance that violates the balance constraint on invoices with 3+ lines.
- Matches Odoo 19.0's default `tax_calculation_rounding_method = round_globally` on `res.company`.
- Display of per-line tax amounts may appear to sum to slightly different totals (±0.01); this is cosmetic and the rounded total is authoritative.
- `round_per_line` was rejected because it requires absorbing a rounding correction line which complicates the balance invariant.
