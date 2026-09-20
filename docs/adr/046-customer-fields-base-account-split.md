# ADR-046: Customer fields split across `base` (address) and `account` (accounting-specific), via each addon's existing ownership idiom

**Status**: Accepted
**Date**: 2026-09-20

## Context

The Customer Database feature (009-customer-database) needs `res.partner` to carry billing
address, a customer/vendor designation, and per-customer AR/currency/payment-term defaults.
`base`'s `ResPartner` already carries `name`/`company_id`/`email`/`phone`/`vat`/`active`/
`is_company` directly as declared `Field`s. `account` already extends the same table with three
unmapped raw columns (`property_account_receivable_id`, `property_account_payable_id`,
`property_payment_term_id`) via its `_PARTNER_FK_COLUMNS` `ALTER TABLE` idiom in
`account_data.py`. Odoo 19 itself splits ownership the same way: `street`/`city`/`zip`/
`country_id`/`vat`/`email`/`phone` live in `base`'s `res_partner.py`, while `customer_rank` and
the `property_*` AR/payment-term fields live in `account/models/partner.py`.

## Decision

Billing-address fields (`street`, `city`, `state_id`, `zip`, `country_id`) are declared directly
on `base`'s `ResPartner` class as plain `Field`s — a same-owner addition. `customer_rank`
(Integer, default 0) and `property_currency_id` (nullable Many2one override) are added the same
way `account` already extends `res_partner` today: two more entries in `account_data.py`'s
`_PARTNER_FK_COLUMNS` list, read/written via raw SQL from `account`'s own layer, not declared
`Field`s on the `base`-owned class. A partner counts as a customer when `customer_rank > 0`.

## Rationale

This split mirrors Odoo's own module boundary exactly. This codebase has no Python `_inherit`
mechanism to add fields to another addon's model class, so its own established substitute — raw
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` plus raw-SQL read/write from the owning addon — is the
existing, proven answer, already used for exactly this purpose (the three `property_*` columns).

## Alternatives Rejected

Declaring `customer_rank`/`property_currency_id` directly on `base`'s `ResPartner` class —
rejected because it would make `base` own an accounting-specific concept it has no reason to know
about, the same reasoning 008-accounting-parity's ADR-039/042 applied when choosing `ALTER TABLE`
over a new `base`-owned field for lock dates and FX-gain-loss accounts. A new `res.partner.customer`
side-table — rejected; it would duplicate the "is a customer" concept Odoo itself keeps as a plain
rank field on the one partner row.

## Consequences / Threat Note

Purely additive — every new column is nullable or defaulted, so existing partner rows are
unaffected. No reverse dependency is introduced: `base` still has zero knowledge of `account`.
