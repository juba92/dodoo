# Quickstart: Vendor Database

Validation scenarios proving the feature end to end. Each uses the JSON-RPC/REST contracts in
`contracts/vendor-database.md` and the fields/rules in `data-model.md`. Run against an existing
dodoo install with `account` already installed (001–009's chart of accounts/journals/customer
infrastructure are already seeded).

## 0. Install / migrate

```bash
python -m dodoo module install account    # additive migration: new res_partner column per data-model.md
```

`module install` re-runs a module's migrations idempotently, so this doubles as the upgrade path
for an already-installed `account`. Confirms: `res_partner` carries `supplier_rank` (new, via
`account`'s `_PARTNER_FK_COLUMNS` extension), nullable/defaulted so existing partner rows
(including existing customers from 009) are unaffected.

## 1. P1 — Maintain the vendor master list (US1)

1. `POST /account/vendor` with `{name: "Global Supply Co", email: "ap@globalsupply.test",
   phone: "+1-555-0200", street: "9 Industrial Way", city: "Riverside", zip: "00001",
   country_id: <id>, vat: "US987654321", property_supplier_payment_term_id: <id>}` — confirm
   `{result: <id>}`, and reading the partner back (`GET /account/partner/{id}`) shows
   `supplier_rank == 1` (Acceptance 1, FR-001/007).
2. `PATCH /account/vendor/{id}` with a new `street` — confirm the read-back reflects it
   immediately (Acceptance 2, FR-002).
3. `POST /account/vendor` with `{}` (no `name`) — confirm `400` with a message identifying the
   missing `name` field (Acceptance 3, FR-001).
4. `write` the partner's `active` to `False` — confirm it drops out of `GET /account/vendors`'
   default active-only response, but a direct `GET /account/partner/{id}` still returns it, and
   its `get_ap_ledger` response is unchanged (Acceptance 4, FR-005).
5. Attempt `unlink` on a partner with a posted bill against it — confirm `400 DodooError`; attempt
   `unlink` on a vendor with no financial history — confirm it succeeds (FR-006, the existing 009
   guard — research.md D7).

## 2. P2 — Find a vendor quickly (US2)

1. Create three vendors with distinct names ("Global Supply Co", "Global Freight", "Beta
   Materials") and VAT numbers. In `vendor-list.js`, type "global" into search — confirm only the
   two Global rows show (Acceptance 1, FR-004).
2. Search by one vendor's exact VAT number — confirm only that vendor shows (Acceptance 2).
3. Search for text matching no vendor — confirm an empty-state message, not an error
   (Acceptance 3, Edge Cases).

## 3. P1 — Review a vendor's AP position (US3)

1. Post two vendor bills (`in_invoice`) against one vendor, totalling e.g. 1000.00, then register
   a partial payment of 125.00 against one of them. `GET /account/partner/{id}/ap-ledger` —
   confirm `balance == "875.00"` and `lines` contains both bills and the payment, each with the
   correct `status` (Acceptance 1/2, FR-008/009).
2. `GET` the AP ledger for a brand-new vendor with no documents — confirm `{"balance": "0.00",
   "lines": []}`, not an error (Acceptance 3, Edge Cases).
3. From `vendor-form.js`'s AP-ledger panel, click a bill row — confirm navigation to
   `#/accounting/move/{move_id}` opens that bill (Acceptance 4, FR-010).
4. Cancel one of the two bills from step 1 before posting (draft-state `action_cancel`) — confirm
   the AP ledger's `balance` is unaffected by it and its line shows `status: "cancelled"` rather
   than disappearing (FR-012, Edge Cases).

## 4. Dual-role check (Edge Cases, FR-015)

1. Take an existing 009 customer (`customer_rank > 0`) and `PATCH /account/vendor/{id}` with
   `{supplier_rank: 1, ...}` — confirm the same partner id now appears in both
   `GET /account/customers` and `GET /account/vendors`, with independent, correctly-scoped
   `GET .../ar-ledger` and `GET .../ap-ledger` responses (no cross-contamination between the two
   ledgers).

## 5. Cross-cutting checks

- Accessibility: run `tests/e2e/test_web_ui_a11y.py`'s vendor-list/vendor-form cases — confirm
  WCAG 2.1 AA contrast, keyboard navigation through search/list rows/AP-ledger links, and
  non-color validation error states (ACC-001…003).
- Performance: `tests/benchmarks/test_accounting_perf.py`'s new case seeds 5,000 AP-ledger lines
  for one vendor and confirms `GET .../ap-ledger` returns in <1s (PERF-002); seeds 10,000 vendors
  and confirms `vendor-list.js`'s initial fetch + client-side filter stays interactive (PERF-001).
  Reuses 009's existing indexes — no new index to seed/verify (research.md D6).
- No regression: re-run `tests/benchmarks/test_accounting_perf.py`'s existing bill/payment posting
  cases — confirm no change, since the AP balance is never written at posting time (PERF-003).
