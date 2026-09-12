# Quickstart: Inventory

Validation scenarios proving the feature end to end. Each uses the JSON-RPC/REST contracts in
`contracts/*.md` and the fields/rules in `data-model.md`. Run after `env.modules.install("stock")`
(which transitively installs `product`) and, for US8, `env.modules.install("stock_account")`.

## 0. Install

```bash
python -m dodoo.cli install stock          # installs product, base, web, localization transitively
python -m dodoo.cli install stock_account  # installs account transitively; adds the 3 category columns (D1)
```

Confirms FR-089's seed data: a default warehouse with its core locations/operation types, a UoM
category with common units, a few product categories, and sample tracked/untracked/service products.

## 1. P1 — Product catalog, variants, units of measure (US1)

1. `product.category.create({name: "Parent"})` then `create({name: "Child", parent_id: <parent>})` —
   confirm the hierarchy is navigable (Acceptance 3).
2. `uom.category.create({name: "Length"})`; `uom.uom.create` a `reference` unit "m" (ratio 1) and a
   `smaller` unit "cm" (ratio 0.01). `GET /product/{id}/uom-convert?qty=250&to_uom_id=<m>` from cm →
   confirm `2.5` (Acceptance 4).
3. `product.template.create({name: "T-Shirt", is_storable: true, ...})`; add attribute lines Color
   (Red/Blue) and Size (S/M) via `POST /product/template/{id}/attribute-lines/apply`; confirm 4
   variants exist (Acceptance 2).
4. Create a `product_type: "service"` template; confirm `GET /product/search` never surfaces an
   on-hand/location field for it (Acceptance 5).

## 2. P1 — Warehouses, locations, operation types (US2)

1. `stock.warehouse.create({..., delivery_steps: "two_steps"})`; `GET
   /stock/warehouse/{id}/topology` — confirm `WH/Stock` and `WH/Output` exist and Delivery Orders'
   default source is `WH/Stock`, an internal type's default destination is `WH/Output` (Acceptance 2).
2. `stock.location.create({parent_id: <WH/Stock>, name: "Shelf A1", usage: "internal"})`; confirm it
   is selectable as a transfer source/destination (Acceptance 3).

## 3. P1 — Receipts, deliveries, internal transfers, returns (US3)

1. Create a Receipts picking for 10 units of a tracked product into `WH/Stock`;
   `POST .../confirm` → `POST .../validate` `{expected_state: "ready"}`; confirm `GET
   /stock/product/{id}/forecast` shows `on_hand: 10` (Independent Test).
2. Create a Delivery Orders picking for 4 units; confirm → reserves 4 (`ready`); validate; confirm
   on-hand drops to 6 (Acceptance 2).
3. Create a Delivery for 20 units with only 6 on hand; confirm → partially reserved (`waiting` on the
   unmet move); validate `{create_backorder: true}` → confirm a backorder picking exists for 14
   (Acceptance 3).
4. `POST /stock/picking/{done_picking_id}/return` on the first delivery; validate the return; confirm
   on-hand increases back (Acceptance 5).
5. Concurrency: call `validate` twice in quick succession with the same `expected_state` — the second
   call returns a conflict error, not a double-decrement (Acceptance 7 / FR-035).

## 4. P2 — Physical inventory adjustments (US4)

1. With 10 on hand, `POST /stock/inventory/count/set` `{lines: [{quant_id, counted_quantity: 8}]}`
   then `POST /stock/inventory/count/apply` — confirm on-hand becomes 8 and a
   `stock.inventory.adjustment.log` row records `qty_before=10, qty_after=8, difference=-2`
   (Independent Test).
2. Apply a count with `counted_quantity` equal to on-hand — confirm no move/log row is created
   (Acceptance 3).

## 5. P2 — Lots, serial numbers, packages (US5)

1. Set a product's `tracking = "serial"`; receive 3 units assigning 3 distinct `stock.lot` rows;
   `GET /stock/traceability/lot/{lot_id}` for one — confirm the receipt event appears.
2. Deliver 1 of the 3 serials; confirm that lot's on-hand is 0 while the other two remain
   (Independent Test).
3. During a receipt of a lot-tracked product, set `package_id` on the move line; `POST
   /stock/package/{id}/move` to a new location; confirm both quants inside the package moved
   together (Acceptance 5).

## 6. P2 — Putaway, storage categories, routes, reordering (US6)

1. Create a `stock.storage.category` with `allow_new_product: "same_product"`; assign two child
   locations. Create a `stock.putaway.rule` from `WH/Stock` to those children (product-specific).
   Receive the product twice; confirm the first and second receipts redirect to different children
   via `GET /stock/putaway/resolve` before and after the first is occupied (Independent Test).
2. Create a `stock.warehouse.orderpoint` with `product_min_qty=5, product_max_qty=20`; drop on-hand to
   3; `POST /stock/orderpoint/run` — confirm a transfer for 17 is created following the product's
   route (Acceptance 4). Run it again before receiving — confirm no duplicate (Acceptance 5).

## 7. P3 — Scrap (US7)

1. With 10 on hand, `stock.scrap.create({quantity: 2, ...})` then `POST
   /stock/scrap/{id}/confirm` — confirm on-hand drops to 8 and the scrap location shows 2
   (Independent Test).
2. Attempt to scrap more than available — confirm rejection (Acceptance 2).

## 8. P3 — Valuation & accounting integration (US8)

1. Set a category's `costing_method = "standard"` and a product's `standard_price = 10`; receive 5
   units; confirm a `stock.valuation.layer` of value 50 and a posted `account.move` debiting
   `property_stock_valuation_account_id` / crediting `property_stock_input_account_id` for 50
   (Independent Test).
2. Switch to `"average"`; receive 5 more at a different cost; confirm the recomputed average; deliver
   4 and confirm the journal entry values them at the new average (Acceptance 2).
3. `GET /stock/valuation/reconcile?...` — confirm `matches: true` against
   `AccountAccount.get_balance` for the valuation account.

## 9. Security & multi-company

- As a user in only `Inventory User`: confirm transfers/counts/scrap succeed but `POST
  /stock/warehouse` and `POST /stock/orderpoint/run` return `403`.
- As a user scoped to company A: confirm `search_read` on every model in `data-model.md` returns
  zero company-B rows, and shared catalog rows (`company_id = NULL`) are visible (SC-002).

## 10. Performance (CI benchmarks)

Run `tests/benchmarks/test_inventory_perf.py` — asserts PERF-001 (catalog search < 500 ms @ 20k
variants), PERF-002 (confirm < 500 ms @ 100 move lines), PERF-003 (forecast < 300 ms @ 100k quants),
PERF-004 (valuation report < 1 s @ 50k open layers).

## 11. Accessibility & E2E

`tests/e2e/test_inventory_ui.py` walks each user story's primary flow via Playwright, asserts zero
WCAG 2.1 AA violations (extends `test_web_ui_a11y.py`), and confirms every workflow action —
including the putaway/reordering editors — is keyboard-operable with no colour-only status indicator
(ACC-001…004).

## Definition of done (maps to spec Success Criteria)

- [ ] SC-001: fresh-install catalog + warehouse + receipt + delivery flow completes in < 15 min.
- [ ] SC-002/SEC-003: 100% company-scope isolation across every model in `data-model.md`.
- [ ] SC-003: validated transfers leave on-hand exactly consistent with move-line quantities.
- [ ] SC-004: every applied count with a difference produces exactly one adjustment move.
- [ ] SC-005: 100% of tracked-product moves carry a lot/serial; traceability lookups are complete.
- [ ] SC-006: 100% of tracked, valued moves produce a layer + balanced journal entry; report
      reconciles to the ledger for standard, average, and FIFO.
- [ ] SC-007: exactly one open replenishment proposal per orderpoint deficit, zero duplicates.
- [ ] SC-008: every transition/workflow action emits a structured JSON log entry.
- [ ] SC-009: PERF-001…004 CI benchmarks pass.
- [ ] SC-010: unit/integration/e2e tests pass for every workflow in `plan.md`'s Project Structure.
- [ ] SC-011: zero WCAG 2.1 AA violations; every action keyboard-operable.
