# Feature Specification: Customer Database

**Feature Branch**: `009-customer-database`

**Created**: 2026-09-20

**Status**: Draft

**Input**: User description: "Add a customer database to the Accounting module: manage customer master records (name, contact info, billing address, tax/VAT number, payment terms, currency) with create/edit/search/list views, each customer linked to their Accounts Receivable ledger showing outstanding balance and invoice/payment history, following Odoo's res.partner (customer_rank) model scoped to this module's existing partner infrastructure."

## Clarifications

### Session 2026-09-20

- Q: The existing partner model has no field marking a partner as a "customer" yet — how should
  that designation work? → A: Add an integer `customer_rank` field (default 0) directly on the
  existing partner model, mirroring Odoo's `res.partner.customer_rank`; a partner counts as a
  customer when `customer_rank > 0`. Chosen because the user's request explicitly names Odoo's
  `customer_rank` model, it fits this module's existing flat-field style on the partner record
  (email/phone/vat already live directly on it), and it avoids introducing a separate
  customer-type table.
- Q: Should the per-customer outstanding AR balance be a stored value kept in sync on every
  posting/reconciliation, or computed on demand? → A: Computed on demand from posted Accounts
  Receivable move lines at read time (not a stored/maintained column). Chosen to match this
  module's existing ledger-query pattern (already used for account and partner-style balance
  reporting) and Odoo's own non-stored `credit`/`debit` compute fields on `res.partner`, and to
  avoid the extra complexity of keeping a stored balance column consistent across invoice, credit
  note, payment, and reconciliation flows.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Maintain the customer master list (Priority: P1)

An accountant needs a single place to create and maintain customer records — legal name, contact
details, billing address, tax/VAT number, default payment terms, and default currency — so that
this information doesn't have to be re-entered on every invoice.

**Why this priority**: Without a maintained customer record, every other capability in this
feature (search, AR ledger, invoicing) has nothing to point to. This is the foundation.

**Independent Test**: Can be fully tested by creating a new customer record with all fields
populated, editing it, and confirming the saved values persist and appear correctly when the
record is reopened. Delivers value on its own as a lightweight customer directory.

**Acceptance Scenarios**:

1. **Given** the customer list view, **When** the accountant creates a new customer with a name,
   email, phone, billing address, VAT number, payment terms, and currency, **Then** the record is
   saved and appears in the customer list with its name and key identifying details visible.
2. **Given** an existing customer record, **When** the accountant edits the billing address and
   saves, **Then** the updated address is reflected immediately in the record and in the list view.
3. **Given** a customer record missing a required field (name), **When** the accountant attempts
   to save, **Then** the system rejects the save and clearly indicates which field is missing.
4. **Given** a customer record, **When** the accountant marks it inactive (archives it) instead of
   deleting it, **Then** it disappears from the default list view but its historical invoices and
   payments remain intact and reachable.

---

### User Story 2 - Find a customer quickly (Priority: P2)

An accountant working with a large customer base needs to search and filter the customer list by
name, VAT number, or contact info to locate the right record without scrolling through hundreds of
entries.

**Why this priority**: A growing customer list is unusable without search; this directly supports
the daily workflow of finding a customer before recording an invoice or payment, but it depends on
customers already existing (User Story 1).

**Independent Test**: Can be fully tested by creating several customers with distinct names/VAT
numbers, then searching by partial name and by VAT number and confirming only matching records are
returned.

**Acceptance Scenarios**:

1. **Given** a customer list with multiple records, **When** the accountant types a partial name
   into the search box, **Then** only customers whose name contains that text are shown.
2. **Given** a customer list, **When** the accountant searches by VAT number, **Then** the matching
   customer (if any) is shown.
3. **Given** a search that matches no customers, **When** the search is run, **Then** the list
   shows an empty state rather than an error.

---

### User Story 3 - Review a customer's Accounts Receivable position (Priority: P1)

An accountant or credit controller opens a customer record and needs to see, at a glance, that
customer's outstanding AR balance and the underlying invoice and payment history that produced it,
without leaving the customer record to run a separate report.

**Why this priority**: This is the capability that distinguishes a "customer database" from a
generic contacts list, and is the primary reason accounting users need this feature — to answer
"how much does this customer owe us, and why?" It is tied for top priority with the master record
itself because the master record has limited standalone value in an accounting context without it.

**Independent Test**: Can be fully tested by posting one or more customer invoices and a partial
payment against a test customer, then opening that customer's record and confirming the displayed
outstanding balance equals invoiced amount minus paid amount, with each invoice and payment listed.

**Acceptance Scenarios**:

1. **Given** a customer with two posted invoices and one payment applied to one of them, **When**
   the accountant opens that customer's AR ledger view, **Then** the outstanding balance shown
   equals the sum of unpaid/partially-paid invoice amounts.
2. **Given** a customer's AR ledger view, **When** the accountant views it, **Then** every posted
   customer invoice, credit note, and payment for that customer is listed with date, document
   reference, amount, and status (paid/partial/open).
3. **Given** a customer with no invoices or payments yet, **When** the accountant opens their AR
   ledger view, **Then** it shows a zero balance and an empty history rather than an error.
4. **Given** a customer's AR ledger entry, **When** the accountant selects an individual invoice or
   payment line, **Then** they can navigate to that document's own record.

---

### Edge Cases

- What happens when a customer is created with a currency that differs from the company's default
  currency? The AR balance must still be presented in a single, clearly labeled currency (see
  Assumptions) rather than silently mixing amounts.
- What happens when the same tax/VAT number is entered for two different customer records? The
  system should warn but not hard-block, since legitimate cases (branches, group entities) exist.
- What happens when an accountant tries to archive a customer that has an outstanding (non-zero) AR
  balance? The system should allow archiving (it only hides the record from default views) but must
  continue to expose the outstanding balance and history so nothing is lost from a collections
  standpoint.
- What happens when a customer record has partial data (e.g., no VAT number, because the customer
  is an individual, not a business)? Only the customer name is required; all other fields are
  optional.
- How does the system handle a search with no query text? It shows the full (active) customer list.
- What happens when an invoice or payment is later voided/cancelled? It must no longer count toward
  the customer's outstanding balance, and the ledger history should reflect its cancelled status
  rather than disappearing silently.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow creating a customer record with: name (required), email, phone,
  billing address (street, city, region/state, postal code, country), tax/VAT number, default
  payment terms, and default currency (all optional except name).
- **FR-002**: System MUST allow editing all fields of an existing customer record.
- **FR-003**: System MUST provide a list view of customers showing, at minimum, name, VAT number,
  and current outstanding AR balance for each customer.
- **FR-004**: System MUST provide a search capability over the customer list that matches on
  customer name and on tax/VAT number.
- **FR-005**: System MUST support archiving (soft-deactivating) a customer record rather than only
  hard deletion, so that historical financial documents referencing that customer remain valid.
- **FR-006**: System MUST prevent hard deletion of a customer record that has any posted invoice,
  credit note, or payment associated with it; archiving MUST remain available in that case.
- **FR-007**: System MUST designate a record as a "customer" via a customer-rank marker on the
  existing partner record (mirroring Odoo's `customer_rank`), rather than a separate customer
  entity, so a single partner record can be a customer, a vendor, or both without duplication.
- **FR-008**: System MUST compute a customer's outstanding Accounts Receivable balance on demand
  from that customer's posted invoices, credit notes, and payments recorded against Accounts
  Receivable, so the figure is always current as of the moment it is viewed without requiring a
  separately maintained stored balance.
- **FR-009**: System MUST display, per customer, a chronological history of that customer's posted
  invoices, credit notes, and payments, each showing date, document reference, amount, and
  paid/partial/open status.
- **FR-010**: System MUST allow navigating from an entry in a customer's AR history to the
  underlying invoice, credit note, or payment record.
- **FR-011**: System MUST default a new customer's payment terms and currency from the company's
  configured defaults when the accountant does not explicitly set them, while still allowing
  per-customer overrides.
- **FR-012**: System MUST exclude cancelled/voided invoices, credit notes, and payments from the
  outstanding AR balance calculation while still showing them in history with a cancelled status.
- **FR-013**: System MUST validate that email addresses, when provided, are in a valid email
  format before saving.
- **FR-014**: System MUST reuse the existing partner record as the underlying entity for a
  customer (i.e., a customer is a partner flagged as a customer), not a separate, disconnected
  entity — so that a partner already known to the system (e.g. as a vendor, or from another module)
  can be promoted to a customer without data duplication.

### Key Entities

- **Customer**: A business-facing role on an existing partner record, marked by customer ranking.
  Carries or references: display name, contact info (email, phone), billing address, tax/VAT
  number, default payment terms, default currency, and active/archived status. Distinct from
  "vendor" (a different role a partner may also hold) and from a bare contact record.
- **Accounts Receivable Ledger (per customer)**: A derived, read-only view — not a separately
  stored entity — composed of the customer's posted invoices, credit notes, and payments that
  affect the Accounts Receivable account, plus the resulting outstanding balance.
- **Payment Terms**: An existing reference entity (already used elsewhere in the module) that a
  customer record links to as its default; not redefined by this feature.
- **Currency**: An existing reference entity (already used elsewhere in the module) that a customer
  record links to as its default; not redefined by this feature.

### Security Requirements

- **SEC-001**: System MUST validate all customer field inputs (name, email, phone, address, VAT
  number) at the point of entry, rejecting malformed or oversized values rather than persisting
  them.
- **SEC-002**: Access to customer records and their AR ledger MUST be restricted to authenticated
  users with accounting access, consistent with access control already enforced for other
  accounting entities in this module.
- **SEC-003**: System MUST comply with OWASP Top 10; a checklist review is REQUIRED before
  implementation, with particular attention to injection risks in customer search.
- **SEC-004**: Customer contact and billing data (personally identifiable information for
  individual customers) MUST only be exposed through the same authenticated, access-controlled
  channels as other financial data in this module — no unauthenticated read access.

### Performance Requirements

- **PERF-001**: The customer list and search views MUST return results within standard interactive
  latency (under 1 second) for a customer base of up to 10,000 records.
- **PERF-002**: A customer's AR ledger view (balance plus history) MUST load within standard
  interactive latency (under 1 second) for a customer with up to 5,000 historical invoices/payments.
- **PERF-003**: No known regressions permitted in existing invoice/payment posting performance as a
  result of maintaining the derived AR balance; relevant benchmarks MUST run in CI.

### Accessibility Requirements

- **ACC-001**: Customer create/edit/search/list/AR-ledger views MUST meet WCAG 2.1 AA color
  contrast ratios (≥ 4.5:1 normal text, ≥ 3:1 large text).
- **ACC-002**: All interactive elements (form fields, search box, list rows, AR ledger line links)
  MUST be keyboard-navigable.
- **ACC-003**: Validation errors (e.g., missing name, invalid email) MUST not rely on color alone
  and MUST expose ARIA labels for assistive technology.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An accountant can create a fully-populated customer record in under 1 minute.
- **SC-002**: An accountant can locate a specific customer among 1,000+ records via search in under
  10 seconds.
- **SC-003**: An accountant can determine a customer's current outstanding balance and see the
  invoice/payment that produced it without navigating away from the customer's own record, in a
  single view.
- **SC-004**: 100% of posted customer invoices, credit notes, and payments for a given customer are
  reflected in that customer's AR ledger history with no manual reconciliation step required.
- **SC-005**: Zero instances of a customer's AR balance diverging from the sum of that customer's
  posted, unreconciled Accounts Receivable transactions (verified by automated tests comparing the
  displayed balance against the underlying ledger).

## Assumptions

- The existing partner infrastructure in this module (already carrying name, company, email,
  phone, VAT) is extended with customer-specific fields, per the resolved `customer_rank` approach
  above, rather than introducing a new, parallel "customer" table.
- Payment terms and currency are selected from the existing payment-terms and currency reference
  data already present in the accounting module (established in prior feature cycles); this feature
  does not define new payment-term or currency behavior.
- "Billing address" for v1 is a single structured address (street, city, region, postal code,
  country) per customer; multiple ship-to/contact sub-addresses per customer are out of scope for
  this feature and may be added later, mirroring Odoo's child-contact model.
- The Accounts Receivable ledger view is a read-only presentation derived from existing invoice,
  credit note, and payment records already posted through this module; this feature does not add
  new invoice/payment entry capability, only a customer-scoped view over what already exists.
- A customer's outstanding balance and history are presented in the customer's default currency
  when the customer's currency differs from the company currency; multi-currency consolidation
  reporting beyond this per-customer view is out of scope.
- Deletion of customer records is restricted to customers with no financial history (per FR-006);
  archiving is the standard removal path for any customer with historical documents, consistent
  with how the module already protects other referenced master data from hard deletion.
- "Search" in this feature is scoped to matching on name and VAT number per the user's explicit
  request; matching on email/phone/address is a reasonable future extension but not required for
  this cycle's success criteria.
