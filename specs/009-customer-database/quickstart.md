# Quickstart: Customer Database

Validation scenarios proving the feature end to end. Each uses the JSON-RPC/REST contracts in
`contracts/customer-database.md` and the fields/rules in `data-model.md`. Run against an existing
dodoo install with `account` already installed (001–008's chart of accounts/journals are already
seeded).

## 0. Install / migrate

```bash
python -m dodoo module install account    # additive migration: new res_partner columns per data-model.md
```

`module install` re-runs a module's migrations idempotently, so this doubles as the upgrade path for
an already-installed `account`. Confirms: `res_partner` carries `street`/`city`/`state_id`/`zip`/
`country_id` (via `base`) and `customer_rank`/`property_currency_id` (via `account`'s
`_PARTNER_FK_COLUMNS` extension), all nullable/defaulted so existing partner rows are unaffected.

## 1. P1 — Maintain the customer master list (US1)

1. `POST /account/partner` with `{name: "Acme Corp", email: "billing@acme.test", phone: "+1-555-0100",
   street: "1 Main St", city: "Springfield", zip: "00000", country_id: <id>, vat: "US123456789,"
   property_payment_term_id: <id>}` — confirm `201`-equivalent `{result: <id>}`, and reading the
   partner back shows `customer_rank == 1` (Acceptance 1, FR-001/007).
2. `PATCH /account/partner/{id}` with a new `street` — confirm the read-back reflects it immediately
   (Acceptance 2, FR-002).
3. `POST /account/partner` with `{}` (no `name`) — confirm `400` with a message identifying the
   missing `name` field (Acceptance 3, FR-001).
4. `write` the partner's `active` to `False` — confirm it drops out of `search_read` with the
   default active-only domain, but a direct `read` by id still returns it, and its `get_ar_ledger`
   response is unchanged (Acceptance 4, FR-005).
5. Attempt `unlink` on a partner with a posted invoice against it — confirm `400 DodooError`; attempt
   `unlink` on a customer with no financial history — confirm it succeeds (FR-006).

## 2. P2 — Find a customer quickly (US2)

1. Create three customers with distinct names ("Acme Corp", "Acme Studios", "Beta LLC") and VAT
   numbers. In `customer-list.js`, type "acme" into search — confirm only the two Acme rows show
   (Acceptance 1, FR-004).
2. Search by one customer's exact VAT number — confirm only that customer shows (Acceptance 2).
3. Search for text matching no customer — confirm an empty-state message, not an error
   (Acceptance 3, Edge Cases).

## 3. P1 — Review a customer's AR position (US3)

1. Post two customer invoices (`out_invoice`) against one customer, totalling e.g. 1500.00, then
   register a partial payment of 250.00 against one of them. `GET
   /account/partner/{id}/ar-ledger` — confirm `balance == "1250.00"` and `lines` contains both
   invoices and the payment, each with the correct `status` (Acceptance 1/2, FR-008/009).
2. `GET` the AR ledger for a brand-new customer with no documents — confirm `{"balance": "0.00",
   "lines": []}`, not an error (Acceptance 3, Edge Cases).
3. From `customer-form.js`'s AR-ledger panel, click an invoice row — confirm navigation to
   `#/accounting/move/{move_id}` opens that invoice (Acceptance 4, FR-010).
4. `action_cancel`/void one of the two invoices from step 1 — confirm the AR ledger's `balance`
   drops by that invoice's amount and its line now shows `status: "cancelled"` rather than
   disappearing (FR-012, Edge Cases).

## 4. Cross-cutting checks

- Accessibility: run `tests/e2e/test_web_ui_a11y.py`'s customer-list/customer-form cases — confirm
  WCAG 2.1 AA contrast, keyboard navigation through search/list rows/AR-ledger links, and non-color
  validation error states (ACC-001…003).
- Performance: `tests/benchmarks/test_accounting_perf.py`'s new case seeds 5,000 AR-ledger lines for
  one customer and confirms `GET .../ar-ledger` returns in <1s (PERF-002); seeds 10,000 customers
  and confirms `customer-list.js`'s initial fetch + client-side filter stays interactive (PERF-001).
- No regression: re-run `tests/benchmarks/test_accounting_perf.py`'s existing invoice/payment
  posting cases — confirm no change, since the AR balance is never written at posting time
  (PERF-003).
