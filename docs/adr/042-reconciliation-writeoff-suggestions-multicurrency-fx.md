# ADR-042: Reconciliation write-offs/suggestions and the multi-currency rate/FX-gain-loss engine

**Status**: Accepted
**Date**: 2026-09-13

## Context

`AccountPartialReconcile.reconcile_lines` only accepted an exact amount capped at
`min(residuals)` — no write-off, no auto-suggestion (FR-020/021). `debit_amount_currency`/
`credit_amount_currency` were declared but never populated or used (FR-022). There was no
currency-rate table at all; `amount_currency` was stored but never converted into company-currency
`debit`/`credit` (FR-023/024). No realized or unrealized exchange gain/loss was ever posted
(FR-025/026).

## Decision

`reconcile_lines` gains `writeoff_account_id`/`writeoff_journal_id` optional parameters; when the
residual doesn't net to zero and a write-off account is supplied, it posts a balancing
`account.move` via the existing create+`action_post` path and reconciles it against the
remaining residual. A new `suggest_matches(env, payment_id)` classmethod ranks open items by
amount closeness then `pg_trgm` reference similarity. `debit_amount_currency`/
`credit_amount_currency` are now populated and drive the residual/full-reconcile check in
transaction-currency terms when either line is foreign-currency. A new `base` model
`ResCurrencyRate` (manual entry only, per spec Clarifications) backs
`AccountMove.action_post`'s new FX-conversion step (`amount_currency × rate → debit/credit`).
`reconcile_lines` additionally detects a realized gain/loss (same `amount_currency`, different
company-currency residual from differing booking rates) and posts it to
`res_company.income_currency_exchange_account_id`/`expense_currency_exchange_account_id`. A new
`AccountMove.revalue_currency_balances` implements the period-end unrealized step, posting one
adjustment move plus its draft next-day reversal.

## Rationale

Routing the write-off and realized-gain/loss postings through the existing `AccountMove.create`/
`action_post` path (rather than raw INSERTs) means both get sequence numbers, balance validation,
and hash-chain coverage for free. Reusing already-declared-but-dead
`debit_amount_currency`/`credit_amount_currency` fields is the minimal fix.

## Alternatives Rejected

Automatic rate-provider integration (ECB feed, etc.) — explicitly ruled out in the spec's
Clarifications; manual entry only. A dedicated `account.exchange.difference` model instead of a
plain journal entry — rejected; Odoo itself posts a normal `account.move` for this.

## Consequences / Threat Note

`currency_id` on a move stops being decorative — any pre-existing foreign-currency move without a
rate entered for its date will fail to convert until a rate is entered (a data-completeness
requirement, not a behavior regression, since no conversion happened before either).
