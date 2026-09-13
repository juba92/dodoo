# Contract: Discounts, Price-Included Tax, Rounding, Debit Notes, Down Payments (US1, US5)

Covers FR-010…FR-016 (ADR-039/040).

## JSON-RPC

| Model | Method | Args/kwargs | Returns | Notes |
|---|---|---|---|---|
| `account.move.line` | `create` / `write` | `{..., discount?: float (0–100)}` | id / `True` | `price_subtotal` is derived net of `discount` inside `_apply_price_defaults` — callers never compute the discounted amount themselves |
| `account.tax` | `create` / `write` | `{..., price_include?: bool}` | id / `True` | **field already existed**; this feature is the first thing that reads it during tax computation |
| `account.tax.repartition.line` | `write` | `{tag_ids: [int, ...]}` | `True` | assigns tax-grid tags |
| `account.account.tag` | `create` / `read` / `search_read` | `{name, applicability?, country_id?}` | id / rows | new model, generic CRUD |
| `res.company` | `write` | `{tax_rounding_method: "round_globally" | "round_per_line"}` | `True` | **field already existed**; this feature is the first thing that reads it during tax computation |

## REST routes

### `POST /account/move/{move_id}/debit-note`

Body: `{}`. Requires the source move to be `posted` and of type `in_invoice`/`out_invoice` (a bill or
an invoice — not a refund/credit-note type). Creates a new move of the **same** `move_type`, copying
lines verbatim (no debit/credit swap — a debit note *increases* the amount owed), sets
`debit_origin_id`. Returns `{result: {debit_note_move_id: int}}`, left in `draft` for the accountant to
review before posting (consistent with how a fresh invoice starts in draft).

### `GET /account/report/tax-report?date_from=&date_to=&company_id=`

Returns tax amounts grouped by grid tag for posted invoices/bills in the range:
`{"grids": [{"tag_name": str, "base": str, "tax": str}], "totals": {"base": str, "tax": str}}`.

## Behavior notes (existing endpoints change internally)

- `POST /account/move/{move_id}/post`: `_compute_tax_lines`/`recompute_totals` now (a) use the
  discount-net `price_subtotal` as the tax base, (b) extract tax from the gross when the applicable
  tax's `price_include=True` instead of adding it on top, (c) round per-line before summing when
  `company.tax_rounding_method == "round_per_line"` (today's global-rounding behavior is unchanged when
  the company field is left at its default `round_globally`). None of these are new response fields —
  they change the *values* of `amount_untaxed`/`amount_tax`/`amount_total` for moves that use a
  discount, a price-included tax, or a `round_per_line` company.
- Down payments: an invoice line with `display_type="down_payment"` and `down_payment_origin_id` set on
  its move is netted automatically against the referenced final invoice's total the first time that
  final invoice is posted (`AccountMove.apply_down_payments`, called from `action_post`) — no separate
  endpoint; the accountant creates the down-payment invoice, posts it, then creates and posts the final
  invoice referencing it via `down_payment_origin_id`.

## Validation models (`account/validators.py`)

```text
class DebitNoteCreate(Payload):
    pass  # empty body

class AccountTagCreate(Payload):
    name: str
    applicability: Literal["taxes"] = "taxes"
    country_id: int | None = None
```
