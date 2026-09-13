# ADR-040: Discount, price-included tax, per-company rounding method, tax grids/report, debit notes, and down payments

**Status**: Accepted
**Date**: 2026-09-13

## Context

Invoice lines had no discount field at all; tax was computed on the raw `debit - credit` value
regardless of any discount; `price_include` was read from the database but never branched on;
`res_company.tax_rounding_method` existed but `_compute_tax_lines` never read it; there was no
tax-grid/report concept; and neither debit notes nor down payments existed (FR-010…016).

## Decision

`account_move_line` gains `discount` (a `Monetary` percentage, 0–100). `_apply_price_defaults`
multiplies by `(1 - discount/100)` when set, so every downstream consumer sees the discounted
subtotal. `AccountMove._compute_tax_lines` is rewritten to: (a) use the discount-net
`price_subtotal` as `base`; (b) branch on each tax's `price_include` — extracting the tax portion
from the gross when `True` instead of adding it on top; (c) branch on
`res_company.tax_rounding_method` for `round_per_line` vs. the existing `round_globally` default.
`AccountTaxRepartitionLine` gains `tag_ids` (Many2many to `account.account.tag`); a new
`AccountReportTax` class aggregates posted tax amounts by tag. `AccountMove` gains
`debit_origin_id` (mirrors `reversed_entry_id`) and `action_create_debit_note` (creates a new
move of the **same** move_type, lines copied verbatim — a debit note adds to the amount owed).
Down payments use a new `display_type` value `"down_payment"` plus `down_payment_origin_id`;
`AccountMove.apply_down_payments`, called from `action_post`, nets a posted down-payment move
against its referenced final invoice.

## Rationale

Every piece attaches to the method that already owns exactly that computation
(`_apply_price_defaults`, `_compute_tax_lines`, `_compute_payment_term_lines`) — no parallel
computation path, which is what made these bugs possible in the first place. A debit note as
"same move_type, positive-copy, linked field" reuses 100% of the existing posting/numbering/
reporting path.

## Alternatives Rejected

A separate `account.debit.note` wizard model — rejected as an extra model/round-trip once
`account.move` already supports every field a debit note needs. Unifying credit and debit notes
under one model — rejected; credit notes already work via `_REVERSE_TYPE`, so unifying would mean
touching proven code for symmetry alone.

## Consequences / Threat Note

Changes the *values* of `amount_untaxed`/`amount_tax`/`amount_total` for moves using a discount,
price-included tax, or `round_per_line` company — existing moves with none of these are
unaffected (SC-007).
