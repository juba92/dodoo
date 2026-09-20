# ADR-049: `supplier_rank` added via `account`'s existing cross-addon idiom; no new `base`-owned fields needed

**Status**: Accepted
**Date**: 2026-09-20

## Context

010-vendor-database needs a way to flag a `res.partner` row as a vendor, mirroring how
009-customer-database flagged one as a customer (`customer_rank`). Billing address and contact
fields (`street`/`city`/`state_id`/`zip`/`country_id`/`email`/`phone`/`vat`) already exist on
`base`'s `ResPartner`, added by 009 — a vendor is the same partner row as a customer, just carrying
a different rank column, not a parallel entity.

## Decision

`supplier_rank` (Integer, default 0) is added as one more entry in `account_data.py`'s
`_PARTNER_FK_COLUMNS` list (`ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS supplier_rank
INTEGER DEFAULT 0`), read/written via raw SQL from `account`'s own model/HTTP layer — the identical
idiom 009's ADR-046 established for `customer_rank`, appended to the same list without touching
`customer_rank`'s existing entry. No billing-address or contact fields are added to `base`'s
`ResPartner`. A partner counts as a vendor when `supplier_rank > 0`, independent of `customer_rank`
(FR-015).

## Rationale

Mirrors Odoo's own module boundary exactly — Odoo declares `supplier_rank` immediately alongside
`customer_rank` in `account/models/partner.py` (`../odoo-19.0/addons/account/models/partner.py:608`),
both conceptually owned by `account`. 009's own research.md D3 explicitly anticipated this exact
addition.

## Alternatives Rejected

Declaring `supplier_rank` on `base`'s `ResPartner` class directly — rejected for the identical
reason 009 rejected it for `customer_rank`: it would make `base` own an accounting-specific
concept it has no reason to know about. A new `res.partner.vendor` side-table — rejected; would
duplicate the single-rank-column concept Odoo itself uses and 009 already proved works for the
customer side.

## Consequences / Threat Note

Additive-only migration (`ADD COLUMN IF NOT EXISTS`), so existing partner rows (including existing
009 customers) are unaffected and no backfill is required. No new attack surface — `supplier_rank`
is only ever set to `0`/`1` by the vendor create/edit routes, both session-authenticated.
