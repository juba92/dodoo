# Feature Specification: Inventory

**Feature Branch**: `007-inventory`

**Created**: 2026-09-13

**Status**: Draft

**Input**: User description: "Add an Inventory module to dodoo that reproduces the Odoo 19.0 'Inventory' application section — Products & Variants, Units of Measure, Warehouses & Locations, Operation Types (Receipts, Delivery Orders, Internal Transfers, Returns), Transfers/Stock Moves, Physical Inventory (Inventory Adjustments/Counts), Lots & Serial Numbers, Packages, Putaway Rules, Storage Categories, Routes & Reordering Rules (Replenishment), Scrap, and Valuation reporting — built as one or more dodoo addons (dodoo/addons/product/, dodoo/addons/stock/) following the existing architecture, and modelled on the Odoo 19.0 product, uom, stock, and stock_account addons. The stock addon depends on the new product addon plus base, web, and localization (005); valuation posts journal entries into the existing account addon (003) the same way stock_account integrates with account in Odoo 19.0."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Product catalog, variants, and units of measure (Priority: P1)

An inventory manager builds the product catalog: categories in a hierarchy, units of measure grouped
by measurement category (e.g. Unit, Weight, Volume), and products. A product is defined once as a
template (name, category, product type — goods, service, or combo — unit of measure, sales/cost
price, barcode) and, when it carries one or more attributes (e.g. Color, Size), the system generates
one product variant per combination of attribute values. Goods can be flagged to track inventory
(stock is followed) or left untracked (always available, no on-hand quantity). Variants can each
override their own barcode and add an extra price on top of the template price.

**Why this priority**: Every other Inventory capability — transfers, counts, lots, routes, valuation
— operates on a product or a variant. Without the catalog and its units of measure there is nothing
to move or value. It delivers standalone value: a working, searchable product catalog on a fresh
install.

**Independent Test**: Create two categories in a parent/child relationship, a unit-of-measure
category with a reference unit and two derived units, and a product template with two attributes
(Color: Red/Blue; Size: S/M) that tracks inventory. Confirm four variants are generated automatically,
each independently priced and barcoded. Create a service product that does not track inventory and
confirm it never asks for a location or on-hand quantity.

**Acceptance Scenarios**:

1. **Given** an inventory manager on the Products screen, **When** they create a product template
   with a category, a unit of measure, a sales price, and a cost, **Then** the template is saved and
   appears in the product list with those values.
2. **Given** a product template with two attributes each carrying two values, **When** the template
   is saved, **Then** exactly four product variants are generated, one per combination, each
   inheriting the template's fields and independently editable for barcode and extra price.
3. **Given** a product category with a parent category, **When** the catalog is browsed, **Then**
   the hierarchy is navigable and a product inherits its category's default settings unless
   overridden.
4. **Given** a unit-of-measure category with a reference unit (ratio 1) and two other units with
   different ratios, **When** a quantity is expressed in one unit, **Then** it converts correctly to
   any other unit in the same category, and a unit from a different category cannot be selected for
   that product.
5. **Given** a product flagged as a service or as a good that does not track inventory, **When** the
   product is viewed, **Then** no on-hand quantity, location, or stock-tracking field is shown or
   requested for it.
6. **Given** two companies, **When** a user scoped to company A lists products, **Then** they see
   catalog entries with no `company_id` (shared) plus company A's own, and never company B's
   company-scoped entries.

---

### User Story 2 - Warehouses, locations, and operation types (Priority: P1)

An inventory manager creates a warehouse for a company, giving it a short code and address. Creating
the warehouse automatically creates its core internal locations (a main stock location, and — per the
warehouse's configured number of receipt/delivery steps — input, quality, output, and packing
locations) and its default operation types (Receipts, Delivery Orders, Internal Transfers, Returns),
each pre-wired with source and destination locations. The manager can also create additional
locations anywhere in the location hierarchy (e.g. a sub-location for a shelf or bin) and additional
operation types.

**Why this priority**: Locations and operation types are the addressing scheme every transfer,
count, putaway rule, and route depends on. They must exist before a single unit of stock can move.

**Independent Test**: Create a warehouse with a two-step delivery configuration. Confirm the
warehouse's stock, output, and view locations exist in the hierarchy, and that its Receipts, Delivery
Orders, Internal Transfers, and Returns operation types exist with correct default source/destination
locations. Create a child location under the stock location and confirm it appears in the hierarchy
and can be selected as a transfer destination.

**Acceptance Scenarios**:

1. **Given** an inventory manager creating a warehouse with a short code, **When** it is saved,
   **Then** its core locations and its Receipts, Delivery Orders, Internal Transfers, and Returns
   operation types are created automatically with sensible default source/destination locations.
2. **Given** a warehouse configured for multi-step receipts (input → quality → stock), **When** the
   configuration is applied, **Then** the intermediate locations and the extra internal operation
   type(s) needed to move goods through the steps are created.
3. **Given** the location hierarchy, **When** a manager creates a child location under an existing
   internal location, **Then** it is available for use as a source or destination on transfers and
   putaway rules.
4. **Given** a location usage type (internal, customer, vendor, inventory loss/adjustment,
   production, transit, view), **When** a location is created, **Then** its usage type governs
   whether it holds on-hand quantities that count as company stock (internal) or not (customer,
   vendor, inventory loss, transit, view).
5. **Given** two warehouses in the same company, **When** an inventory manager compares their
   operation types, **Then** each warehouse's operation types reference only that warehouse's own
   locations.
6. **Given** two companies, **When** a user scoped to company A opens Warehouses, **Then** only
   company A's warehouses, locations, and operation types are shown.

---

### User Story 3 - Receipts, delivery orders, internal transfers, and returns (Priority: P1)

A warehouse worker processes incoming goods, outgoing goods, and internal movements as Transfers. A
transfer belongs to an operation type, lists one or more stock moves (product, quantity, source and
destination location), and progresses through draft → waiting → confirmed → ready → done (or
cancelled). When enough on-hand quantity exists at the source location, a transfer becomes ready
(reserved); validating it records the actual quantities moved, updates on-hand quantities at both
locations, and — if less than the full quantity was moved — offers to create a backorder for the
remainder. A done transfer can be reversed with a Return, which creates a new transfer moving the
same quantity back with source and destination swapped.

**Why this priority**: Moving stock in, out, and around the warehouse is the core operational
transaction of the Inventory app; every other capability (counts, lots, packages, routes, scrap,
valuation) attaches to or is triggered by a stock move.

**Independent Test**: Create a receipt for 10 units of a tracked product into the warehouse's stock
location and validate it; confirm on-hand at the stock location becomes 10. Create a delivery order
for 4 units; confirm it reserves 4 units, validate it, and confirm on-hand drops to 6. Create a
delivery for 20 units of a product with only 6 on hand; confirm it cannot fully reserve, validate the
6 available, and confirm a backorder is offered for the remaining 14. Return the first delivery's
done quantity and confirm on-hand increases back accordingly.

**Acceptance Scenarios**:

1. **Given** a Receipts operation type, **When** a worker creates a transfer with a product and
   quantity and validates it, **Then** the transfer moves to done, on-hand quantity at the
   destination location increases by the validated quantity, and a stock move line records the
   actual quantity moved.
2. **Given** a Delivery Orders transfer for a quantity that is fully available at the source
   location, **When** the transfer is confirmed, **Then** it reserves the quantity and becomes ready;
   validating it decreases on-hand at the source location by the moved quantity.
3. **Given** a transfer for a quantity greater than what is available, **When** it is confirmed,
   **Then** it reserves only the available quantity and remains partially waiting; validating the
   reserved quantity offers to create a backorder transfer for the unmet remainder.
4. **Given** an Internal Transfers operation type, **When** a worker moves a quantity from one
   internal location to another, **Then** on-hand decreases at the source and increases at the
   destination with no net change to total company stock.
5. **Given** a done transfer, **When** a worker creates a Return for it, **Then** a new transfer is
   created with the same product and quantity, source and destination locations swapped, ready to be
   validated.
6. **Given** a transfer in the ready or waiting state, **When** it is cancelled, **Then** its
   reservation is released, on-hand quantities are unaffected, and the transfer is marked cancelled.
7. **Given** a transfer being validated concurrently by two actions, **When** the second validation
   runs, **Then** it is rejected with a conflict error if the transfer's state has already moved on.
8. **Given** two companies, **When** a user scoped to company A lists transfers, **Then** only
   transfers on company A's warehouses are shown.

---

### User Story 4 - Physical inventory adjustments (Priority: P2)

An inventory manager periodically counts stock. Filtering on-hand quantities by location, product, or
category, they enter a counted quantity for each on-hand line. Applying the count creates an
inventory-adjustment stock move for every line whose counted quantity differs from the system's
on-hand quantity, correcting on-hand to match the count and recording the discrepancy (positive or
negative) against the warehouse's inventory-loss location.

**Why this priority**: Physical counts are how discrepancies between system and physical stock are
reconciled; they depend on on-hand quantities existing (US1–US3) but are otherwise a self-contained
periodic operation.

**Independent Test**: With 10 units on hand for a product at a location, set a counted quantity of 8
and apply the adjustment; confirm on-hand becomes 8 and an inventory-adjustment move recorded a
decrease of 2 against the inventory-loss location. Set another product's counted quantity for a
location with zero on-hand to 5 and apply it; confirm on-hand becomes 5.

**Acceptance Scenarios**:

1. **Given** an on-hand quantity at a location, **When** a manager enters a counted quantity lower
   than on-hand and applies it, **Then** on-hand decreases to the counted value and the difference is
   recorded as a move to the inventory-loss location.
2. **Given** an on-hand quantity at a location, **When** a manager enters a counted quantity higher
   than on-hand and applies it, **Then** on-hand increases to the counted value and the difference is
   recorded as a move from the inventory-loss location.
3. **Given** a counted quantity equal to the current on-hand, **When** the count is applied, **Then**
   no adjustment move is created.
4. **Given** a count filtered to one location and one product category, **When** it is opened,
   **Then** only on-hand lines matching that location and category are listed for counting.
5. **Given** an inventory adjustment applied, **When** the adjustment history is viewed, **Then** the
   before/after quantities, the difference, and the acting user are recorded.

---

### User Story 5 - Lots, serial numbers, and packages (Priority: P2)

For products that need traceability, an inventory manager sets a tracking mode: none, by lot (a
batch shared by many units), or by serial number (a unique number per unit). Receiving or producing
such a product requires assigning a lot or serial number on the move line, and on-hand quantity is
then tracked per lot/serial in addition to per location. Any transfer, count, or scrap involving a
tracked product records which lot/serial moved. Multiple products (or multiple units of the same
lot) can be grouped into a Package that moves and is looked up as a single unit; a package can itself
be relocated as a whole. Given a lot, a serial number, or a package, the system can list every
transfer that received, moved, or shipped it (traceability).

**Why this priority**: Lots, serial numbers, and packages add optional but common traceability and
handling-unit capability on top of the core transfer flow (US3); they are not required for the
simplest possible warehouse operation.

**Independent Test**: Set a product to serial-number tracking. Receive 3 units, assigning 3 distinct
serial numbers. Confirm on-hand shows 3 units across 3 serials at the location. Deliver 1 unit,
selecting one of the serials; confirm that serial's on-hand becomes zero while the other two remain.
Pack two units of a lot-tracked product into a package during a receipt; confirm the package can be
moved as a unit to another location and both quants move together. Look up the serial that was
delivered and confirm both its receipt and its delivery appear in its traceability history.

**Acceptance Scenarios**:

1. **Given** a product tracked by serial number, **When** a receipt move line is validated without a
   serial number, **Then** it is rejected; validating with a unique serial number succeeds.
2. **Given** a product tracked by lot, **When** several receipts use the same lot, **Then** on-hand
   for that lot accumulates across the receipts, and per-lot on-hand can be listed for that product.
3. **Given** a serial-tracked product, **When** a lot/serial is assigned a serial number already used
   by another on-hand unit of the same product, **Then** the assignment is rejected.
4. **Given** a transfer, **When** a worker assigns a destination package to one or more move lines
   and validates, **Then** those quantities are on hand inside that package at the destination
   location.
5. **Given** a package containing quants at a location, **When** the whole package is moved to
   another location, **Then** every quant inside the package moves to the new location together.
6. **Given** a lot, a serial number, or a package, **When** its traceability is viewed, **Then**
   every transfer that received, moved, or shipped it is listed in chronological order.

---

### User Story 6 - Putaway rules, storage categories, routes, and reordering rules (Priority: P2)

An inventory manager configures automatic stock placement and replenishment. A Storage Category
defines a capacity limit (e.g. maximum weight, maximum number of packages, or "only one product per
location") that can be applied to one or more locations. A Putaway Rule says: when a given product
(or its category) arrives at a given source location, redirect it to a specific destination
location (a child of the source), optionally restricted to child locations belonging to a storage
category with available capacity. A Route is a named, ordered sequence of Rules that determine how a
product is resupplied (e.g. a multi-step warehouse route, or a resupply-from-another-warehouse
route); a route can be set on a product, a category, or a warehouse. A Reordering Rule sets a minimum
and maximum quantity for a product at a warehouse/location; when forecasted on-hand (on-hand plus
incoming minus outgoing) drops below the minimum, replenishment is triggered up to the maximum,
following the product's applicable route.

**Why this priority**: Putaway, storage categories, routes, and reordering automate placement and
replenishment on top of the manual transfer flow (US3); they change *where* and *when* stock moves
but are not required to move a single unit of stock end to end.

**Independent Test**: Define a storage category limiting a location to one product at a time and
assign it to two child locations. Define a putaway rule sending a given product from the main stock
location to whichever assigned child location currently has capacity. Receive the product twice and
confirm each receipt is redirected to a different child location once the first is occupied. Define a
reordering rule with a minimum of 5 and a maximum of 20 for a product; drop on-hand to 3 and run
replenishment; confirm a receipt-style transfer for 17 units is proposed/created following the
product's route.

**Acceptance Scenarios**:

1. **Given** a putaway rule for a product from a source location to a destination location, **When**
   a receipt brings that product into the source location, **Then** the move line's destination is
   redirected to the putaway destination.
2. **Given** a storage category limiting a location's capacity, **When** a putaway destination would
   exceed that capacity, **Then** the rule skips to the next eligible destination location or, if
   none has capacity, leaves the original destination unchanged.
3. **Given** a route with an ordered set of rules assigned to a product, **When** a replenishment or
   multi-step transfer is triggered for that product, **Then** the moves generated follow the route's
   rules in order.
4. **Given** a reordering rule with a minimum and maximum quantity, **When** forecasted on-hand for
   that product/location falls below the minimum, **Then** a replenishment proposal for enough
   quantity to reach the maximum is generated, following the product's route.
5. **Given** a reordering rule that has already generated a pending replenishment covering the
   deficit, **When** the scheduler runs again before it is received, **Then** it does not create a
   duplicate replenishment for the same deficit.
6. **Given** a product with no route resolving to a supply source, **When** replenishment is
   attempted, **Then** it is reported as unresolved rather than silently doing nothing.

---

### User Story 7 - Scrap (Priority: P3)

A warehouse worker records damaged, expired, or lost stock as Scrap: a product (and, if tracked, a
lot/serial), a quantity, and a source location. Confirming the scrap moves that quantity out of the
source location's on-hand into the warehouse's scrap location and cannot be undone by editing the
scrap record.

**Why this priority**: Scrap is a narrow, low-frequency write-off operation that depends on on-hand
quantities (US1–US3) already existing; it does not block or gate any other capability.

**Independent Test**: With 10 units on hand at a location, scrap 2 units and confirm on-hand drops to
8 and 2 units now show on hand at the scrap location. Attempt to scrap more than the available
quantity and confirm it is rejected.

**Acceptance Scenarios**:

1. **Given** on-hand quantity at a location, **When** a worker scraps a quantity at or below on-hand,
   **Then** on-hand at the source location decreases by that quantity and the scrap location's
   on-hand increases by the same amount.
2. **Given** a scrap request for more than the available on-hand quantity, **When** it is confirmed,
   **Then** it is rejected.
3. **Given** a lot/serial-tracked product, **When** it is scrapped, **Then** the specific lot/serial
   scrapped is recorded.
4. **Given** a confirmed (done) scrap, **When** it is viewed, **Then** it cannot be edited or
   deleted, only viewed as history.

---

### User Story 8 - Inventory valuation and accounting integration (Priority: P3)

An inventory manager configures, per product category, a costing method (standard price, average
cost, or FIFO) for valuing on-hand stock. Every stock move that brings a tracked product into or out
of the company's internal locations creates a valuation record capturing the quantity and the unit
cost/value used, and — because valuation is posted to accounting — a matching journal entry debiting
and crediting the category's configured stock, and stock-interim accounts (received/delivered) in
the existing accounting ledger. An inventory manager can view a valuation report showing current
stock value by product/category/location and the full history of valuation layers, and can reconcile
it against the posted journal entries.

**Why this priority**: Valuation is a downstream reporting/accounting concern layered on top of
every move already recorded by US3–US7; it changes how a move is *costed*, not whether it happens, so
it is safe to deliver last.

**Independent Test**: Set a product category to standard-price costing with a cost of 10. Receive 5
units; confirm a valuation layer for 5 × 10 = 50 is created and a journal entry debits the stock
valuation account and credits the stock-interim-received account for 50. Change costing to average
and receive 5 more units at a different unit cost; confirm the average cost recalculates and a
delivery of 4 units values out at the current average with a matching journal entry crediting stock
valuation and debiting the stock-interim-delivered account. Open the valuation report and confirm
current stock value matches the sum of remaining valuation layers, which matches the accounting
ledger's stock valuation account balance.

**Acceptance Scenarios**:

1. **Given** a product category set to standard-price costing, **When** a tracked product it applies
   to is received, **Then** a valuation layer records quantity × standard cost, and a balanced
   journal entry is posted between the category's stock valuation and stock-interim-received
   accounts.
2. **Given** a product category set to average-cost costing, **When** additional units are received
   at a different unit cost, **Then** the product's average cost is recalculated across all on-hand
   quantity and used to value the next outgoing move.
3. **Given** a product category set to FIFO costing, **When** units are delivered, **Then** they are
   valued out of the oldest remaining incoming valuation layer(s) first, consuming those layers in
   order.
4. **Given** a delivery or internal consumption of a tracked product, **When** it is validated,
   **Then** a valuation layer and a balanced journal entry are posted crediting the stock valuation
   account and debiting the stock-interim-delivered (or consumption) account.
5. **Given** an inventory adjustment or scrap of a tracked, valued product, **When** it is applied,
   **Then** a valuation layer and a balanced journal entry are posted against an inventory-loss
   account for the value of the adjustment/scrap.
6. **Given** the valuation report, **When** it is opened for a company, **Then** the total value
   shown per product/category equals the sum of that product/category's remaining valuation layers,
   and reconciles to the stock valuation account's ledger balance in the accounting addon.
7. **Given** a product not flagged to track inventory, **When** it moves, **Then** no valuation layer
   or journal entry is created for it.

---

### Edge Cases

- **Zero or negative quantities**: a transfer, receipt, count, or scrap line with a zero or negative
  requested quantity is rejected before confirmation.
- **Negative on-hand**: by default a delivery or internal transfer cannot reduce a location's on-hand
  below zero for a tracked product; an inventory adjustment or a scrap request exceeding on-hand is
  likewise rejected (except the inventory-adjustment and inventory-loss counterpart locations
  themselves, which may go negative as the mirror side of a correction).
- **Partial reservation / backorder decline**: when a transfer is validated with less than the full
  demanded quantity reserved, the actor may either create a backorder for the remainder or explicitly
  close the transfer without one; a declined backorder does not silently lose the unmet demand — it
  is recorded as not-done.
- **Untracked product moved**: a service product, or a good not flagged to track inventory, can
  appear on a transfer line for informational/document purposes but never affects on-hand quantity,
  reservation, or valuation.
- **Lot/serial required but missing**: validating a move line for a lot- or serial-tracked product
  without a lot/serial value is rejected.
- **Duplicate serial on hand**: assigning a serial number that is already on hand (not yet consumed)
  for the same product is rejected; the same serial number may be reused only after it has left all
  on-hand locations.
- **Putaway rule with no available destination**: if every eligible destination location for a
  putaway rule is at storage-category capacity, the move keeps its original (non-redirected)
  destination rather than failing.
- **Circular or self-referential route rules**: a rule whose destination location is also configured
  as its own source (directly or transitively within the same route) is rejected at configuration
  time.
- **Reordering rule already covered**: a reordering rule does not generate a second replenishment
  proposal while an existing incoming transfer already covers the computed deficit.
- **Costing method change mid-history**: changing a category's costing method applies prospectively
  to moves from that point forward; existing valuation layers and their journal entries are not
  retroactively recomputed.
- **Return of a partially consumed package/lot**: returning a done transfer that moved part of a
  package or lot returns exactly the quantity/lot originally moved by that transfer, not the whole
  package or lot.
- **Multi-company**: every operational record (product's company-scoped fields, warehouse, location,
  operation type, transfer, stock move, quant, lot/serial, package, putaway rule, storage category,
  route, reordering rule, scrap, valuation layer, journal entry) is scoped to a company and only
  visible within that company's scope. Catalog configuration (product category, unit of measure,
  storage category) carries an optional `company_id`: `NULL` = shared across all companies, a set
  value = visible only in that company — matching Odoo 19.0, where `product.category` and `uom.uom`
  are global and `stock.warehouse` / `stock.location` are company-scoped.

## Requirements *(mandatory)*

### Functional Requirements

#### Product catalog, categories, variants, and units of measure (P1)

- **FR-001**: The system MUST provide a Product Category record supporting an optional parent
  category, forming a navigable hierarchy, with an optional `company_id` (`NULL` = shared).
- **FR-002**: The system MUST provide a Unit of Measure Category record and a Unit of Measure record
  belonging to it, where exactly one unit per category is the reference unit (ratio 1) and every
  other unit carries a ratio used to convert to and from the reference unit.
- **FR-003**: The system MUST reject selecting a unit of measure for a product's purchase/alternate
  unit fields that does not belong to the same unit-of-measure category as the product's primary
  unit.
- **FR-004**: The system MUST provide a Product Template record with a name, category, product type
  (goods, service, or combo), a "track inventory" flag (applicable only to goods), a primary unit of
  measure, a sales price, a cost, and a barcode.
- **FR-005**: The system MUST provide Product Attribute, Attribute Value, and Attribute Line records
  allowing a template to declare one or more attributes with a set of possible values.
- **FR-006**: Saving a template with attribute lines MUST generate one Product Variant per
  combination of attribute values (the Cartesian product across attributes), and MUST NOT duplicate
  variants already generated for an unchanged combination when attribute lines are edited.
- **FR-007**: A Product Variant MUST allow overriding its own barcode and adding an extra price on top
  of its template's sales price; all other fields are inherited from the template unless the template
  has no attributes, in which case the template has exactly one implicit variant.
- **FR-008**: A product not flagged to track inventory (a service, or a good with the flag off) MUST
  NOT expose or require an on-hand quantity, location, or stock-tracking (lot/serial) setting.
- **FR-009**: The system MUST provide full-text/barcode search across products and variants, filtered
  by category, product type, and tracking status.
- **FR-010**: Product Template and Product Variant records MUST carry an optional `company_id`
  (`NULL` = shared across all companies).
- **FR-011**: The system MUST maintain a computed on-hand quantity, a reserved (outgoing) quantity,
  and a forecasted quantity (on-hand + incoming − outgoing) per tracked product/variant, aggregated
  across locations and per location.
- **FR-012**: All Products, Categories, and Units of Measure screens MUST render translated labels and
  support right-to-left layout when the active language is right-to-left, consistent with features
  002 and 005.

#### Warehouses, locations, and operation types (P1)

- **FR-013**: The system MUST provide a Warehouse record (name, short code, company, address) whose
  creation automatically creates its core internal locations and its default Receipts, Delivery
  Orders, Internal Transfers, and Returns operation types.
- **FR-014**: A Warehouse MUST support a configurable number of receipt steps (one/two/three) and
  delivery steps (one/two/three); changing the configuration MUST create or remove the corresponding
  intermediate locations and operation types and rewire the default routes accordingly.
- **FR-015**: The system MUST provide a Location record supporting an optional parent location,
  forming a navigable hierarchy, and a usage type of internal, customer, vendor, inventory
  loss/adjustment, production, transit, or view.
- **FR-016**: Only locations of usage type internal MUST count toward a company's on-hand stock
  totals; customer, vendor, inventory-loss, production, transit, and view locations never do.
- **FR-017**: The system MUST provide an Operation Type record (name, code — incoming, outgoing, or
  internal — warehouse, default source location, default destination location, naming sequence) and
  MUST seed Receipts, Delivery Orders, Internal Transfers, and Returns per warehouse.
- **FR-018**: An Operation Type MUST support configuration flags controlling whether reservation is
  automatic on confirmation and whether creating a backorder is required, optional, or never offered.
- **FR-019**: A Returns transfer MUST reference the operation type appropriate to reversing its
  originating transfer's direction (e.g. a delivery's return uses a Returns-configured incoming
  operation type).
- **FR-020**: Warehouse, Location, and Operation Type records MUST be company-scoped: a user only
  sees warehouses, locations, and operation types for companies they are allowed to access.
- **FR-021**: The system MUST expose a location-hierarchy presentation and a warehouse configuration
  screen showing its locations and operation types together.
- **FR-022**: All Warehouses/Locations screens MUST render translated labels and support
  right-to-left layout when the active language is right-to-left.

#### Transfers and stock moves — receipts, deliveries, internal transfers, returns (P1)

- **FR-023**: The system MUST provide a Transfer (Picking) record belonging to an operation type,
  with a state of draft, waiting, confirmed, ready (assigned), done, or cancelled, and MUST record
  every state transition.
- **FR-024**: A Transfer MUST contain one or more Stock Move records (product, demanded quantity,
  unit of measure, source location, destination location) derived from the transfer's operation type
  defaults, overridable per move.
- **FR-025**: Confirming a Transfer MUST attempt to reserve the demanded quantity of each tracked
  move from available (on-hand minus already-reserved) quantity at the source location, moving fully
  reserved transfers to ready and partially/unreservable ones to waiting.
- **FR-026**: The system MUST provide a Stock Move Line record capturing the actual quantity moved for
  a stock move, with its own source/destination location (which MAY differ from the move's, e.g. via
  putaway), and, where applicable, a lot/serial and a package.
- **FR-027**: Validating a Transfer MUST create/confirm its move lines' quantities, update on-hand
  quantity at the source location (decrease) and the destination location (increase) for each tracked
  product, and set the transfer to done.
- **FR-028**: Validating a Transfer with less than the full demanded quantity reserved and available
  MUST offer to create a Backorder transfer, on the same operation type, for the unmet remainder;
  declining leaves the shortfall recorded as not delivered.
- **FR-029**: The system MUST reject any move line whose validated quantity would reduce an internal
  location's on-hand for a tracked product below zero.
- **FR-030**: The system MUST provide a Return action on a done Transfer that creates a new Transfer
  with the same product(s) and quantities, source and destination swapped, for validation.
- **FR-031**: Cancelling a Transfer in draft, waiting, confirmed, or ready state MUST release any
  reservation, leave on-hand quantities unaffected, and set it to cancelled; a done Transfer MUST NOT
  be cancellable (a Return MUST be used instead).
- **FR-032**: Transfer, Stock Move, and Stock Move Line records MUST be company-scoped through their
  warehouse/operation type.
- **FR-033**: The system MUST provide list and kanban-by-stage presentations of transfers grouped by
  operation type and state.
- **FR-034**: The system MUST provide a per-product/variant forecast presentation (incoming,
  outgoing, on-hand, forecasted) usable when planning or reviewing a transfer.
- **FR-035**: Every Transfer state transition and validation MUST re-check the record's current state
  server-side against the expected source state before applying it, rejecting with a conflict error
  and no side effects if the record has already moved on (concurrent/stale action).
- **FR-036**: All Transfers screens MUST render translated labels and support right-to-left layout
  when the active language is right-to-left.

#### Physical inventory adjustments (P2)

- **FR-037**: The system MUST provide an inventory-count presentation listing current on-hand
  quantities, filterable by location, product, category, and lot/serial, with an editable counted
  quantity per line.
- **FR-038**: Applying a count MUST, for every line whose counted quantity differs from on-hand,
  create an inventory-adjustment stock move between the location and the warehouse's inventory-loss
  location for the difference, and update on-hand to the counted value.
- **FR-039**: Applying a count line whose counted quantity equals current on-hand MUST NOT create an
  adjustment move.
- **FR-040**: The system MUST record, for every applied adjustment, the before quantity, after
  (counted) quantity, the computed difference, the acting user, and the timestamp.
- **FR-041**: A count MUST support lot/serial-tracked products by allowing the counted quantity to be
  entered per lot/serial at a location, not only per product.
- **FR-042**: Inventory-adjustment history MUST be viewable per location and per product, and MUST be
  company-scoped through the warehouse.

#### Lots and serial numbers (P2)

- **FR-043**: The system MUST provide a per-product tracking mode of none, by lot, or by serial
  number; the mode MUST NOT be changeable once the product has any on-hand quantity or move history.
- **FR-044**: The system MUST provide a Lot/Serial Number record (number, product, company, optional
  expiration/manufacture date) and MUST enforce a unique lot/serial number per product.
- **FR-045**: A move line for a product tracked by lot or serial number MUST require a lot/serial
  value before it can be validated; the system MUST reject validation otherwise.
- **FR-046**: A move line for a product tracked by serial number MUST require the validated quantity
  to be exactly one unit per serial number and MUST reject assigning a serial number currently on
  hand elsewhere for the same product.
- **FR-047**: The system MUST maintain on-hand quantity per lot/serial in addition to per location,
  and MUST expose it in the product's on-hand and forecast presentations.
- **FR-048**: The system MUST provide a traceability lookup for a given lot/serial number returning
  every transfer (and its move lines) that received, moved, or shipped it, in chronological order.
- **FR-049**: Lot/Serial records MUST be company-scoped through their product/company relationship.

#### Packages (P2)

- **FR-050**: The system MUST provide a Package record (name/barcode, optional package type) that a
  move line can reference as its destination package, grouping the quantities placed into it at a
  single location.
- **FR-051**: The system MUST provide a Package Type record (name, optional maximum weight) usable to
  classify packages.
- **FR-052**: The system MUST provide a "move package" action that relocates every quant currently
  inside a package to a new destination location as a single transfer operation.
- **FR-053**: The system MUST support nesting a package's contents from a source package into a
  different destination package during a transfer (repackaging).
- **FR-054**: The system MUST include a given lot/serial or package in the traceability lookup (FR-048)
  covering any transfer that moved it as part of a package.

#### Putaway rules and storage categories (P2)

- **FR-055**: The system MUST provide a Storage Category record (name, optional maximum weight,
  optional maximum number of packages, and an "allow new product" policy: always / only if same
  product / only if same lot) assignable to one or more locations.
- **FR-056**: The system MUST provide a Putaway Rule record matching a source location and a product
  or product category, and specifying a destination location (a descendant of the source),
  optionally restricted to destinations carrying a given storage category.
- **FR-057**: When a move line's destination is being resolved for a product entering a source
  location that has one or more applicable putaway rules, the system MUST redirect the destination to
  the first eligible rule's destination location that has available capacity per its storage category
  (if any); if none has capacity, the original destination is kept unchanged.
- **FR-058**: A more specific putaway rule (matching the exact product) MUST take precedence over a
  less specific one (matching only the product's category) for the same source location.
- **FR-059**: Storage Category and Putaway Rule records MUST be company-scoped through their
  location(s).

#### Routes and reordering rules — replenishment (P2)

- **FR-060**: The system MUST provide a Route record (name, applicable to products, product
  categories, and/or warehouses) containing an ordered set of Rule records.
- **FR-061**: A Rule record MUST specify an action (move within the warehouse, or resupply from
  another warehouse/location), a source location, a destination location, and the operation type used
  to generate its moves.
- **FR-062**: The system MUST reject a Rule configuration whose destination location is also its own
  source, directly or transitively, within the same route.
- **FR-063**: The system MUST provide a Reordering Rule record (product, warehouse or location,
  minimum quantity, maximum quantity, and a multiple/rounding quantity) triggering replenishment when
  forecasted quantity (on-hand + incoming − outgoing) for that product/location falls below the
  minimum.
- **FR-064**: Triggering replenishment for a Reordering Rule MUST generate a proposal/transfer for a
  quantity that brings forecasted quantity up to at least the maximum, rounded up to the configured
  multiple, following the product's applicable route to determine the supplying operation type and
  source location.
- **FR-065**: The system MUST NOT generate a duplicate replenishment for a Reordering Rule while an
  existing, not-yet-received incoming transfer already covers the computed deficit.
- **FR-066**: If a product's applicable route resolves to no usable supply source, the system MUST
  report the reordering rule as unresolved rather than silently skipping it.

#### Scrap (P3)

- **FR-067**: The system MUST provide a Scrap record (product, optional lot/serial, quantity, source
  location, target scrap location, reason) with a state of draft or done.
- **FR-068**: Confirming a Scrap record MUST decrease on-hand at the source location and increase
  on-hand at the scrap location by the scrapped quantity, and MUST reject a quantity exceeding
  available on-hand at the source.
- **FR-069**: A done Scrap record MUST NOT be editable or deletable; it remains visible as history.
- **FR-070**: Scrap records MUST be company-scoped through their source location's warehouse.

#### Valuation and accounting integration (P3)

- **FR-071**: The system MUST provide a costing method setting (standard price, average cost, or
  FIFO) per product category, applied to every tracked product in that category.
- **FR-072**: The system MUST provide a Stock Valuation Layer record created for every validated
  stock move of a tracked product, capturing the quantity, unit cost, total value, and — for
  FIFO — the remaining (unconsumed) quantity and value of that layer.
- **FR-073**: An incoming move (from a non-internal location into an internal one) for a
  standard-price product MUST value the layer at the product's current standard cost; for an
  average-cost product MUST recompute and store the new weighted-average cost across all on-hand
  quantity; for a FIFO product MUST open a new layer at the move's unit cost.
- **FR-074**: An outgoing move (from an internal location to a non-internal one, or a consumption)
  for a standard-price or average-cost product MUST value the layer at the current standard/average
  cost; for a FIFO product MUST consume the oldest remaining layer(s) first, splitting a layer when
  the outgoing quantity is smaller than its remaining quantity.
- **FR-075**: Every valuation layer MUST post a balanced journal entry into the accounting addon
  (003) crediting/debiting the product category's configured stock valuation account against its
  stock-interim-received account (incoming), its stock-interim-delivered account (outgoing), or an
  inventory-loss/adjustment account (physical-inventory and scrap adjustments), mirroring how
  `stock_account` posts against `account` in Odoo 19.0.
- **FR-076**: A product not flagged to track inventory MUST NOT generate a valuation layer or a
  journal entry for any move.
- **FR-077**: The system MUST provide a Valuation Report presenting current stock value by product,
  by category, and by location, computed as the sum of each product's remaining (unconsumed)
  valuation layers.
- **FR-078**: The Valuation Report's total per product/category MUST reconcile to the balance of that
  category's stock valuation account in the accounting addon's ledger.
- **FR-079**: Changing a product category's costing method MUST apply only to valuation layers
  created from that point forward; existing layers and their posted journal entries are not
  retroactively recomputed.

#### Security groups and record rules (cross-cutting)

- **FR-080**: The system MUST define Inventory security groups: Inventory User and Inventory
  Manager/Administrator (Manager is a superset of User).
- **FR-081**: A user in only the Inventory User group MUST be able to create and validate transfers,
  counts, lots/serials, packages, and scrap within their company scope, but MUST NOT create or edit
  warehouses, operation types, putaway rules, storage categories, routes, reordering rules, or
  costing-method configuration.
- **FR-082**: An Inventory Manager MUST be able to manage all Inventory configuration (warehouses,
  locations, operation types, putaway rules, storage categories, routes, reordering rules, costing
  methods) in addition to everything an Inventory User can do, within their company scope.
- **FR-083**: Every record rule MUST enforce company scope in addition to the role-based conditions
  above.
- **FR-084**: Posting a valuation journal entry MUST use the accounting addon's own posting
  authorization (no Inventory-only user may post directly to accounting outside the valuation flow
  defined here).

#### Navigation and menus (cross-cutting)

- **FR-085**: The Inventory area MUST contribute its own top-level application menu with sub-menus
  for Products, Product Variants, Product Categories, Units of Measure, Warehouses, Locations,
  Operation Types (Receipts, Delivery Orders, Internal Transfers, Returns), Physical Inventory, Lots &
  Serial Numbers, Packages, Putaway Rules, Storage Categories, Routes, Reordering Rules, Scrap, and
  Valuation Report, following the menu-contribution pattern already used by the accounting addon. The
  generic metadata-driven model sidebar from feature 002 MUST remain available and MUST NOT be
  removed by this feature. Menu entries MUST be gated by the viewer's Inventory User/Manager group.

#### Input validation, logging, workflow integrity (cross-cutting)

- **FR-086**: Every HTTP/RPC entry point that creates or mutates a product, warehouse, location,
  operation type, transfer, stock move, count, lot/serial, package, putaway rule, storage category,
  route, reordering rule, scrap, or valuation record MUST validate inputs at the boundary using
  whitelist-based validation before any processing; unknown fields and out-of-range/negative
  quantities MUST be rejected.
- **FR-087**: Every workflow state transition (transfer confirm/reserve/validate/cancel/return, count
  apply, scrap confirm, reordering-rule trigger) MUST emit a structured JSON log entry carrying a
  correlation ID, the actor, the record, and the from/to state.
- **FR-088**: All workflow actions MUST be authorization-checked server-side: the acting user MUST
  hold a group (Inventory User/Manager) that permits the action, else it is denied and logged.
- **FR-089**: A fresh install MUST seed sample data: a default warehouse with its core locations and
  operation types, a unit-of-measure category with common units (e.g. Unit, Dozen; Kilogram, Gram),
  a few product categories, and a handful of sample products (a tracked good, an untracked good, and
  a service) demonstrating the catalog without requiring configuration before first use.

### Key Entities *(include if feature involves data)*

- **Product Category**: hierarchical grouping of products with an optional `company_id`; carries a
  default costing method for valuation. Modelled on Odoo `product.category`.
- **Unit of Measure Category / Unit of Measure**: a measurement family (e.g. Weight) and its member
  units, one of which is the reference unit; other units carry a conversion ratio. Modelled on Odoo
  `uom.category`, `uom.uom`.
- **Product Template**: the shared definition of a sellable/stockable thing — name, category, type
  (goods/service/combo), track-inventory flag, unit of measure, prices, barcode, optional
  `company_id`. Modelled on Odoo `product.template`.
- **Product Attribute / Attribute Value / Attribute Line**: the taxonomy used to generate variants.
  Modelled on Odoo `product.attribute`, `product.attribute.value`, `product.template.attribute.line`.
- **Product Variant**: one sellable/stockable combination of a template's attribute values, with its
  own barcode and extra price. Modelled on Odoo `product.product`.
- **Warehouse**: a company's physical stock location, short code, and its default step configuration
  and address; owns a set of core Locations and Operation Types. Modelled on Odoo `stock.warehouse`.
- **Location**: a node in the hierarchical storage tree with a usage type (internal, customer,
  vendor, inventory loss, production, transit, view). Modelled on Odoo `stock.location`.
- **Operation Type (Picking Type)**: a named kind of transfer (Receipts, Delivery Orders, Internal
  Transfers, Returns) with default source/destination locations and a naming sequence. Modelled on
  Odoo `stock.picking.type`.
- **Transfer (Picking)**: a document grouping one or more Stock Moves under an operation type, with a
  workflow state. Modelled on Odoo `stock.picking`.
- **Stock Move**: a planned movement of a product/quantity between two locations belonging to a
  Transfer. Modelled on Odoo `stock.move`.
- **Stock Move Line**: the actual quantity moved for a Stock Move, with its own locations, lot/serial,
  and package. Modelled on Odoo `stock.move.line`.
- **Quant**: the on-hand quantity of a product at a location, optionally further keyed by lot/serial
  and package; the basis for reservation and on-hand reporting. Modelled on Odoo `stock.quant`.
- **Lot/Serial Number**: a batch (lot) or unique unit (serial) identifier for a tracked product.
  Modelled on Odoo `stock.lot`.
- **Package / Package Type**: a container grouping quants that can be moved and looked up as a unit;
  Package Type classifies packages (e.g. by max weight). Modelled on Odoo `stock.quant.package`,
  `stock.package.type`.
- **Storage Category**: capacity constraints (max weight, max packages, same-product/lot policy)
  assignable to locations. Modelled on Odoo `stock.storage.category`.
- **Putaway Rule**: redirects a product/category arriving at a source location to a destination
  location, optionally storage-category-gated. Modelled on Odoo `stock.putaway.rule`.
- **Route / Rule**: a named sequence of Rules (source, destination, operation type, action) applied to
  products/categories/warehouses to determine supply paths. Modelled on Odoo `stock.route`,
  `stock.rule`.
- **Reordering Rule (Orderpoint)**: min/max quantities per product/warehouse triggering
  replenishment. Modelled on Odoo `stock.warehouse.orderpoint`.
- **Scrap**: a write-off document moving a quantity from a source location to the scrap location.
  Modelled on Odoo `stock.scrap`.
- **Stock Valuation Layer**: the value (quantity × unit cost) attributed to one stock move, and — for
  FIFO — its remaining unconsumed quantity/value. Modelled on Odoo `stock.valuation.layer`.
- **Security groups**: Inventory User, Inventory Manager (nested). Bound to record rules combining
  role conditions with company scope. Modelled on Odoo `stock.group_stock_user` /
  `stock.group_stock_manager`.
- **Reused core entities**: `res.company` (multi-company scope), `res.currency` (valuation and price
  amounts), `res.lang` (translation/RTL from 005), and the accounting addon's `account.move` /
  `account.move.line` / `account.account` (journal entries and accounts targeted by valuation
  postings, FR-075/FR-078) and `account.journal` (the stock journal postings are made into). The
  feature adds new records and rules; it introduces no parallel currency or company structures.

### Security Requirements

- **SEC-001**: The system MUST validate all inputs at HTTP/RPC boundaries using whitelist-based
  validation (allowed field names, types, enumerations, and non-negative numeric ranges) before any
  downstream processing, for every Inventory create/update/action endpoint.
- **SEC-002**: The system MUST enforce least-privilege: the Inventory User/Manager groups MUST gate
  every model operation and workflow action, and no endpoint may perform an action the acting user's
  groups do not permit.
- **SEC-003**: Record rules MUST ensure company scope on every Inventory record (product's
  company-scoped fields, warehouse, location, operation type, transfer, move, quant, lot/serial,
  package, putaway rule, storage category, route, reordering rule, scrap, valuation layer): a user
  restricted to one company MUST see zero records scoped to another company.
- **SEC-004**: Every mutation and workflow endpoint MUST require an authenticated session and MUST
  re-check authorization server-side on each call (no reliance on the client hiding actions).
- **SEC-005**: The system MUST comply with OWASP Top 10; a checklist review is REQUIRED before
  implementation, with attention to A01 Broken Access Control (cross-company stock/valuation
  exposure), A03 Injection (free-text notes, barcodes, seed data), and A04 Insecure Design (quantity
  and valuation manipulation via replay or stale-state transitions).
- **SEC-006**: Valuation journal-entry posting MUST reuse the accounting addon's existing posting
  authorization and balance-integrity checks; Inventory workflows MUST NOT write directly to ledger
  balances outside that mechanism.
- **SEC-007**: Secrets and credentials MUST NOT appear in source, seed data, logs, or error messages.

### Performance Requirements

- **PERF-001**: The product/variant catalog list/search MUST return the first page (50 records) in
  under 500 ms for a catalog of up to 20,000 variants under normal load, including filters on
  category, product type, and tracking status.
- **PERF-002**: Confirming a transfer (reservation) MUST complete in under 500 ms for a transfer of
  up to 100 stock move lines under normal load.
- **PERF-003**: Computing a product's on-hand/forecasted quantity across locations MUST complete in
  under 300 ms for a product with up to 100,000 quant records under normal load.
- **PERF-004**: The valuation report MUST compute in under 1 s for up to 50,000 open valuation layers
  under normal load.
- **PERF-005**: No known regressions permitted; benchmark tests for the catalog list/search path, the
  transfer reservation path, and the valuation report MUST run in CI, and the existing targets of
  features 001–006 MUST be unaffected.

### Accessibility Requirements

- **ACC-001**: All Inventory screens MUST meet WCAG 2.1 AA colour-contrast ratios (≥ 4.5:1 normal
  text, ≥ 3:1 large text) in both left-to-right and right-to-left layouts.
- **ACC-002**: All interactive elements — including the operation-type kanban, the reordering-rule
  and putaway-rule editors, and every workflow action button — MUST be fully keyboard-operable.
- **ACC-003**: Workflow state (transfer state, count status, scrap state, reordering-rule
  under/over-minimum status, valuation reconciliation status) MUST NOT be conveyed by colour alone;
  text/ARIA labels MUST accompany every status indicator.
- **ACC-004**: Right-to-left layouts MUST preserve a logical keyboard tab order and set the correct
  language and direction attributes, consistent with feature 005.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a fresh install an inventory manager can create a product with variants, a
  warehouse, and complete a receipt followed by a delivery, in under 15 minutes with no configuration
  beyond the seeded data.
- **SC-002**: 100% of Inventory records enforce company scope — a user restricted to one company sees
  zero records from another company across products' company-scoped fields, warehouses, locations,
  transfers, quants, lots/serials, packages, routes, reordering rules, scrap, and valuation layers.
- **SC-003**: 100% of validated transfers leave on-hand quantities exactly consistent with the sum of
  their move lines' quantities at both source and destination locations, with zero instances of
  negative on-hand for a tracked product outside the inventory-loss/adjustment counterpart location.
- **SC-004**: 100% of applied inventory counts whose counted quantity differs from on-hand produce an
  adjustment move that brings on-hand to exactly the counted value.
- **SC-005**: 100% of lot/serial-tracked product moves carry a lot/serial value, and a traceability
  lookup for any lot/serial/package returns every transfer that touched it with no omissions.
- **SC-006**: 100% of stock moves for a tracked, valued product produce a valuation layer and a
  balanced journal entry; the valuation report's total per product/category matches the accounting
  addon's stock valuation account balance to the last posted entry, verified for standard, average,
  and FIFO costing methods.
- **SC-007**: A reordering rule whose forecasted quantity falls below its minimum produces exactly
  one open replenishment proposal per deficit, with zero duplicate proposals while the deficit remains
  covered by an existing incoming transfer.
- **SC-008**: Every state transition and workflow action across all eight areas produces a structured
  JSON log entry with a correlation ID, actor, record identifier, and from/to state — verified for
  100% of transition types.
- **SC-009**: The catalog list/search returns the first 50 results in under 500 ms at 20,000 variants,
  and the valuation report computes in under 1 s at 50,000 open layers, measured by CI benchmarks.
- **SC-010**: Every workflow (transfer lifecycle + backorder + return, inventory count, lot/serial
  traceability, package move, putaway redirection, route-driven replenishment, scrap, and valuation
  posting) has passing unit, integration, and end-to-end tests.
- **SC-011**: An automated accessibility audit of every Inventory screen reports zero WCAG 2.1 AA
  violations in both left-to-right and right-to-left layouts, and every workflow action is operable
  by keyboard alone.

## Assumptions

- **Odoo reference**: the spec reproduces the *behaviour* of the Odoo 19.0 `product`, `uom`, `stock`,
  and `stock_account` addons (models, field groupings, states, menus, security groups, workflows, and
  costing methods). Where the Odoo source is available at `../odoo-19.0` it is the authority on
  field-level detail during planning; where it is not, established Odoo 19.0 semantics are assumed
  (e.g. the `product.template.type` in {goods, service, combo} plus a separate `is_storable`/"track
  inventory" flag introduced in Odoo 17 and carried into 19.0).
- **Architecture**: implemented as `dodoo/addons/product/` (Categories + Units of Measure + Templates
  + Attributes + Variants) and `dodoo/addons/stock/` (Warehouses/Locations/Operation Types +
  Transfers/Moves + Physical Inventory + Lots/Serials + Packages + Putaway/Storage Categories +
  Routes/Reordering + Scrap), on the existing FastAPI routing, SQLAlchemy Core async, Pydantic v2,
  vanilla-JS SPA, and the ORM / view / record-rule patterns from 001-erp-core and 002-web-ui. `stock`
  depends on `product`, `base`, `web`, and `localization` (005). Valuation (Stock Valuation Layers and
  journal posting into `account`, 003) may be delivered inside `stock` or split into a separate
  `dodoo/addons/stock_account/` addon depending on `stock` + `account` — mirroring Odoo's own split —
  the exact addon boundary for valuation is a planning decision; the delivered functional scope is
  `product` + `stock` + valuation as described in User Story 8.
- **Scope boundaries — explicitly out of scope**: Purchase (RFQs/purchase orders) and Sales (sales
  orders) apps and any automatic document generation into them; Manufacturing (bills of materials,
  manufacturing orders) and any "manufacture" route action; batch/wave picking
  (`stock.picking.batch`); barcode-scanner mobile UI/app (barcode remains a plain text/data field
  searchable in the catalog, not a scanning workflow); landed costs; quality-control checks
  (`stock.picking` quality alerts); delivery-slip/report printing beyond the valuation report;
  dropshipping and cross-docking beyond standard multi-step warehouse routes; expiration-driven
  removal strategies (FEFO) beyond FIFO costing; periodic/manual (non-automated) valuation; chatter,
  activities, and digest emails. These may be later features.
- **Replenishment without Purchase/Manufacturing**: because the Purchase and Manufacturing apps are
  out of scope for this feature, a Route's rule that would normally create a purchase RFQ or a
  manufacturing order instead resolves to a direct Receipt-type transfer from the Vendor location (or
  a resupply transfer from another warehouse for an inter-warehouse route), using the product's
  current cost as the receipt's valuation input. This preserves the stock-movement and replenishment
  behaviour of Odoo 19.0's routes while deferring vendor/RFQ management to a future Purchase feature.
- **Costing/valuation is automated only**: every product category valued for accounting purposes uses
  Odoo's "automated" (perpetual, real-time journal entry) valuation; Odoo's alternative "manual"
  (periodic, no automatic journal entries) valuation mode is not offered — this keeps the valuation
  scope aligned with the stock_account integration the feature explicitly asks for.
- **Multi-company & localization**: every operational record carries `company_id` and obeys the
  multi-company visibility rules from 001; screens consume the translation/RTL layer from 002/005.
  Catalog configuration (product category, unit of measure, storage category) carries an optional,
  nullable `company_id` (shared when `NULL`), matching Odoo 19.0.
- **Dependencies**: requires the completed 001-erp-core (models, record rules, HTTP/RPC, users &
  groups), 002-web-ui (generic view architecture, list/form/kanban/sidebar), 003-accounting (journal,
  account, account move/move line — the posting target for valuation), and 005-localization-settings
  (language, RTL, company currency/country). No dependency on 004-accounting-ui or 006-human-resources.
- **ADRs to be filed during planning**: the transfer/reservation state engine; the putaway/storage
  capacity resolution algorithm; the route/reordering-rule replenishment resolution (including the
  no-Purchase-app fallback); and the costing-method (standard/average/FIFO) valuation engine and its
  journal-posting integration with `account`.

## Out of Scope

- Purchase (RFQs, purchase orders, vendor bill matching) and Sales (sales orders, delivery from sales)
  apps; this feature only reproduces the Inventory application's own capabilities.
- Manufacturing: bills of materials, manufacturing orders, and any "manufacture" route action.
- Batch/wave picking (`stock.picking.batch`) and any multi-transfer batch console.
- Barcode-scanner mobile UI/app; barcode remains a searchable data field only.
- Landed costs, quality-control checks/alerts, and delivery-slip/label report printing.
- Dropshipping and cross-docking flows beyond standard multi-step warehouse routes.
- Expiration-based removal strategies (FEFO) and shelf-life alerting beyond FIFO costing.
- Periodic/manual (non-automated) inventory valuation.
- Chatter/message threads, activity scheduling, digest emails, and notification emails.
- Additional Inventory-adjacent Odoo apps not listed (e.g. Barcode app, Quality, Purchase, Sales,
  Manufacturing, Repairs).
