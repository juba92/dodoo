# Feature Specification: Vendor Database

**Feature Branch**: `010-vendor-database`

**Created**: 2026-09-20

**Status**: Draft

**Input**: User description: "Add a vendor database to the Accounting module: manage
vendor/supplier master records (name, contact info, billing address, tax/VAT number, payment
terms, currency) with create/edit/search/list views, each vendor linked to their Accounts Payable
ledger showing outstanding balance and bill/payment history, following Odoo's res.partner
(supplier_rank) model scoped to this module's existing partner infrastructure."

## Clarifications

### Session 2026-09-20

- Q: The existing partner model has no field marking a partner as a "vendor" yet — how should that
  designation work? → A: Add an integer `supplier_rank` field (default 0) directly on the existing
  partner model, mirroring Odoo's `res.partner.supplier_rank` and this module's own precedent of
  `customer_rank` (009-customer-database); a partner counts as a vendor when `supplier_rank > 0`.
  Chosen because the user's request explicitly names Odoo's `supplier_rank`, it reuses the exact
  flat-field-on-partner idiom this module already established for `customer_rank`, and it keeps a
  single partner record able to be a customer, a vendor, or both without duplication.
- Q: Should the per-vendor outstanding AP balance be a stored value kept in sync on every
  posting/reconciliation, or computed on demand? → A: Computed on demand from posted Accounts
  Payable move lines at read time (not a stored/maintained column), mirroring this module's
  existing customer AR ledger (`get_ar_ledger`) and aged-payables report query patterns. Chosen for
  consistency with the proven AR ledger approach and to avoid keeping a stored balance column
  consistent across vendor bill, credit note, payment, and reconciliation flows.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Maintain the vendor master list (Priority: P1)

An accountant needs a single place to create and maintain vendor/supplier records — legal name,
contact details, billing address, tax/VAT number, default payment terms, and default currency — so
that this information doesn't have to be re-entered on every vendor bill.

**Why this priority**: Without a maintained vendor record, every other capability in this feature
(search, AP ledger, bill entry) has nothing to point to. This is the foundation.

**Independent Test**: Can be fully tested by creating a new vendor record with all fields
populated, editing it, and confirming the saved values persist and appear correctly when the
record is reopened. Delivers value on its own as a lightweight vendor directory.

**Acceptance Scenarios**:

1. **Given** the vendor list view, **When** the accountant creates a new vendor with a name, email,
   phone, billing address, VAT number, payment terms, and currency, **Then** the record is saved
   and appears in the vendor list with its name and key identifying details visible.
2. **Given** an existing vendor record, **When** the accountant edits the billing address and
   saves, **Then** the updated address is reflected immediately in the record and in the list view.
3. **Given** a vendor record missing a required field (name), **When** the accountant attempts to
   save, **Then** the system rejects the save and clearly indicates which field is missing.
4. **Given** a vendor record, **When** the accountant marks it inactive (archives it) instead of
   deleting it, **Then** it disappears from the default list view but its historical bills and
   payments remain intact and reachable.

---

### User Story 2 - Find a vendor quickly (Priority: P2)

An accountant working with a large vendor base needs to search and filter the vendor list by name,
VAT number, or contact info to locate the right record without scrolling through hundreds of
entries.

**Why this priority**: A growing vendor list is unusable without search; this directly supports the
daily workflow of finding a vendor before recording a bill or payment, but it depends on vendors
already existing (User Story 1).

**Independent Test**: Can be fully tested by creating several vendors with distinct names/VAT
numbers, then searching by partial name and by VAT number and confirming only matching records are
returned.

**Acceptance Scenarios**:

1. **Given** a vendor list with multiple records, **When** the accountant types a partial name into
   the search box, **Then** only vendors whose name contains that text are shown.
2. **Given** a vendor list, **When** the accountant searches by VAT number, **Then** the matching
   vendor (if any) is shown.
3. **Given** a search that matches no vendors, **When** the search is run, **Then** the list shows
   an empty state rather than an error.

---

### User Story 3 - Review a vendor's Accounts Payable position (Priority: P1)

An accountant opens a vendor record and needs to see, at a glance, that vendor's outstanding AP
balance and the underlying bill and payment history that produced it, without leaving the vendor
record to run a separate report.

**Why this priority**: This is the capability that distinguishes a "vendor database" from a generic
contacts list, and is the primary reason accounting users need this feature — to answer "how much
do we owe this vendor, and why?" It is tied for top priority with the master record itself because
the master record has limited standalone value in an accounting context without it.

**Independent Test**: Can be fully tested by posting one or more vendor bills and a partial payment
against a test vendor, then opening that vendor's record and confirming the displayed outstanding
balance equals billed amount minus paid amount, with each bill and payment listed.

**Acceptance Scenarios**:

1. **Given** a vendor with two posted bills and one payment applied to one of them, **When** the
   accountant opens that vendor's AP ledger view, **Then** the outstanding balance shown equals the
   sum of unpaid/partially-paid bill amounts.
2. **Given** a vendor's AP ledger view, **When** the accountant views it, **Then** every posted
   vendor bill, credit note, and payment for that vendor is listed with date, document reference,
   amount, and status (paid/partial/open).
3. **Given** a vendor with no bills or payments yet, **When** the accountant opens their AP ledger
   view, **Then** it shows a zero balance and an empty history rather than an error.
4. **Given** a vendor's AP ledger entry, **When** the accountant selects an individual bill or
   payment line, **Then** they can navigate to that document's own record.

---

### Edge Cases

- What happens when a vendor is created with a currency that differs from the company's default
  currency? The AP balance must still be presented in a single, clearly labeled currency (see
  Assumptions) rather than silently mixing amounts.
- What happens when the same tax/VAT number is entered for two different vendor records? The system
  should warn but not hard-block, since legitimate cases (branches, group entities) exist.
- What happens when an accountant tries to archive a vendor that has an outstanding (non-zero) AP
  balance? The system should allow archiving (it only hides the record from default views) but must
  continue to expose the outstanding balance and history so nothing is lost from a payables
  standpoint.
- What happens when a vendor record has partial data (e.g., no VAT number, because the vendor is an
  individual, not a business)? Only the vendor name is required; all other fields are optional.
- How does the system handle a search with no query text? It shows the full (active) vendor list.
- What happens when a bill or payment is later voided/cancelled? It must no longer count toward the
  vendor's outstanding balance, and the ledger history should reflect its cancelled status rather
  than disappearing silently.
- What happens when a partner is already a customer (`customer_rank > 0`) and is now also marked as
  a vendor? Both roles coexist on the same partner record; the vendor record shown is the same
  underlying partner, now additionally carrying a positive `supplier_rank`, with its own independent
  AP ledger alongside that partner's existing AR ledger.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow creating a vendor record with: name (required), email, phone,
  billing address (street, city, region/state, postal code, country), tax/VAT number, default
  payment terms, and default currency (all optional except name).
- **FR-002**: System MUST allow editing all fields of an existing vendor record.
- **FR-003**: System MUST provide a list view of vendors showing, at minimum, name, VAT number, and
  current outstanding AP balance for each vendor.
- **FR-004**: System MUST provide a search capability over the vendor list that matches on vendor
  name and on tax/VAT number.
- **FR-005**: System MUST support archiving (soft-deactivating) a vendor record rather than only
  hard deletion, so that historical financial documents referencing that vendor remain valid.
- **FR-006**: System MUST prevent hard deletion of a vendor record that has any posted bill, credit
  note, or payment associated with it; archiving MUST remain available in that case.
- **FR-007**: System MUST designate a record as a "vendor" via a supplier-rank marker on the
  existing partner record (mirroring Odoo's `supplier_rank`), rather than a separate vendor entity,
  so a single partner record can be a customer, a vendor, or both without duplication.
- **FR-008**: System MUST compute a vendor's outstanding Accounts Payable balance on demand from
  that vendor's posted bills, credit notes, and payments recorded against Accounts Payable, so the
  figure is always current as of the moment it is viewed without requiring a separately maintained
  stored balance.
- **FR-009**: System MUST display, per vendor, a chronological history of that vendor's posted
  bills, credit notes, and payments, each showing date, document reference, amount, and
  paid/partial/open status.
- **FR-010**: System MUST allow navigating from an entry in a vendor's AP history to the underlying
  bill, credit note, or payment record.
- **FR-011**: System MUST default a new vendor's payment terms and currency from the company's
  configured defaults when the accountant does not explicitly set them, while still allowing
  per-vendor overrides.
- **FR-012**: System MUST exclude cancelled/voided bills, credit notes, and payments from the
  outstanding AP balance calculation while still showing them in history with a cancelled status.
- **FR-013**: System MUST validate that email addresses, when provided, are in a valid email format
  before saving.
- **FR-014**: System MUST reuse the existing partner record as the underlying entity for a vendor
  (i.e., a vendor is a partner flagged as a vendor), not a separate, disconnected entity — so that a
  partner already known to the system (e.g. as a customer, or from another module) can be promoted
  to a vendor without data duplication.
- **FR-015**: System MUST allow a single partner record to carry both a positive `customer_rank` and
  a positive `supplier_rank` simultaneously, exposing an independent AP ledger and an independent AR
  ledger for that same underlying partner.

### Key Entities

- **Vendor**: A business-facing role on an existing partner record, marked by supplier ranking.
  Carries or references: display name, contact info (email, phone), billing address, tax/VAT
  number, default payment terms, default currency, and active/archived status. Distinct from
  "customer" (a different role a partner may also hold) and from a bare contact record.
- **Accounts Payable Ledger (per vendor)**: A derived, read-only view — not a separately stored
  entity — composed of the vendor's posted bills, credit notes, and payments that affect the
  Accounts Payable account, plus the resulting outstanding balance.
- **Payment Terms**: An existing reference entity (already used elsewhere in the module) that a
  vendor record links to as its default; not redefined by this feature.
- **Currency**: An existing reference entity (already used elsewhere in the module) that a vendor
  record links to as its default; not redefined by this feature.

### Security Requirements

- **SEC-001**: System MUST validate all vendor field inputs (name, email, phone, address, VAT
  number) at the point of entry, rejecting malformed or oversized values rather than persisting
  them.
- **SEC-002**: Access to vendor records and their AP ledger MUST be restricted to authenticated
  users with accounting access, consistent with access control already enforced for other
  accounting entities in this module.
- **SEC-003**: System MUST comply with OWASP Top 10; a checklist review is REQUIRED before
  implementation, with particular attention to injection risks in vendor search.
- **SEC-004**: Vendor contact and billing data (personally identifiable information for individual
  vendors) MUST only be exposed through the same authenticated, access-controlled channels as other
  financial data in this module — no unauthenticated read access.

### Performance Requirements

- **PERF-001**: The vendor list and search views MUST return results within standard interactive
  latency (under 1 second) for a vendor base of up to 10,000 records.
- **PERF-002**: A vendor's AP ledger view (balance plus history) MUST load within standard
  interactive latency (under 1 second) for a vendor with up to 5,000 historical bills/payments.
- **PERF-003**: No known regressions permitted in existing bill/payment posting performance; since
  the AP balance is computed on demand (not stored), it MUST NOT add any extra write or lookup to
  the bill/payment posting path itself. Relevant benchmarks MUST run in CI.

### Accessibility Requirements

- **ACC-001**: Vendor create/edit/search/list/AP-ledger views MUST meet WCAG 2.1 AA color contrast
  ratios (≥ 4.5:1 normal text, ≥ 3:1 large text).
- **ACC-002**: All interactive elements (form fields, search box, list rows, AP ledger line links)
  MUST be keyboard-navigable.
- **ACC-003**: Validation errors (e.g., missing name, invalid email) MUST not rely on color alone
  and MUST expose ARIA labels for assistive technology.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An accountant can create a fully-populated vendor record in under 1 minute.
- **SC-002**: An accountant can locate a specific vendor among 1,000+ records via search in under 10
  seconds.
- **SC-003**: An accountant can determine a vendor's current outstanding balance and see the
  bill/payment that produced it without navigating away from the vendor's own record, in a single
  view.
- **SC-004**: 100% of posted vendor bills, credit notes, and payments for a given vendor are
  reflected in that vendor's AP ledger history with no manual reconciliation step required.
- **SC-005**: Zero instances of a vendor's AP balance diverging from the sum of that vendor's
  posted, unreconciled Accounts Payable transactions (verified by automated tests comparing the
  displayed balance against the underlying ledger).

## Assumptions

- The existing partner infrastructure in this module (already carrying name, company, email, phone,
  VAT, and — since 009-customer-database — `customer_rank`) is extended with vendor-specific fields,
  per the resolved `supplier_rank` approach above, rather than introducing a new, parallel "vendor"
  table.
- Payment terms and currency are selected from the existing payment-terms and currency reference
  data already present in the accounting module (established in prior feature cycles); this feature
  does not define new payment-term or currency behavior.
- "Billing address" for v1 is a single structured address (street, city, region, postal code,
  country) per vendor; multiple remit-to/contact sub-addresses per vendor are out of scope for this
  feature and may be added later, mirroring Odoo's child-contact model.
- The Accounts Payable ledger view is a read-only presentation derived from existing vendor bill,
  credit note, and payment records already posted through this module (the `in_invoice`/
  `in_refund`/`in_receipt` move types and `liability_payable` account type already exist); this
  feature does not add new bill/payment entry capability, only a vendor-scoped view over what
  already exists.
- A vendor's outstanding balance and history are presented in the vendor's default currency when the
  vendor's currency differs from the company currency; multi-currency consolidation reporting beyond
  this per-vendor view is out of scope.
- Deletion of vendor records is restricted to vendors with no financial history (per FR-006);
  archiving is the standard removal path for any vendor with historical documents, consistent with
  how the module already protects other referenced master data from hard deletion, and with how
  009-customer-database handles the same concern for customers.
- "Search" in this feature is scoped to matching on name and VAT number per the user's explicit
  request; matching on email/phone/address is a reasonable future extension but not required for
  this cycle's success criteria.
