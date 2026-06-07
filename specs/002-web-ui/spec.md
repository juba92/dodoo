# Feature Specification: Dodoo Web UI

**Feature Branch**: `002-web-ui`

**Created**: 2026-06-06

**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Sign In (Priority: P1)

An unauthenticated user opens the app in a browser and is shown a login screen. They enter their credentials, and upon success are redirected to the home screen. If credentials are wrong, a clear error message appears. The session persists across page refreshes until the user explicitly logs out or the session expires.

**Why this priority**: Nothing else in the UI is usable without authentication. This is the entry gate to the entire application.

**Independent Test**: Open the app, enter `admin` / `admin`, and be taken to the home screen. Entering wrong credentials keeps the user on the login page with an error message.

**Acceptance Scenarios**:

1. **Given** a user is not logged in, **When** they open the app, **Then** they see the login page and cannot access any other screen.
2. **Given** the login page is shown, **When** the user enters valid credentials and submits, **Then** they are taken to the home screen and their session is saved.
3. **Given** the login page is shown, **When** the user enters invalid credentials, **Then** an error message is shown and they remain on the login page.
4. **Given** a user is logged in, **When** they refresh the page, **Then** they remain logged in and on their current screen.
5. **Given** a user is logged in, **When** they click Logout, **Then** their session is destroyed and they are returned to the login page.

---

### User Story 2 — Home Screen & App Menu (Priority: P2)

After signing in, the user lands on a home screen that shows the installed modules as a grid of tiles. Each tile has the module name and a representative icon. Clicking a tile opens that module's overview page, showing the models available within it.

**Why this priority**: Provides orientation — the user needs to know what is installed and how to navigate to each area.

**Independent Test**: After login, the home screen shows at least the `base` module tile. Clicking it opens the module overview page at `#/module/base`.

**Acceptance Scenarios**:

1. **Given** a logged-in user on the home screen, **When** they view the page, **Then** they see one tile per installed module with name and icon.
2. **Given** the home screen, **When** the user clicks a module tile, **Then** they are taken to that module's overview page (`#/module/:name`).
3. **Given** the home screen, **When** no modules other than base are installed, **Then** the base module tile is still shown.

---

### User Story 3 — List View (Priority: P2)

Within a module, the user can browse records of any model in a paginated table. Column headers match field names. A search bar filters the displayed records. The user can click any row to open its form view.

**Why this priority**: List view is the primary way users discover and navigate to records — foundational to all data management workflows.

**Independent Test**: Navigate to Users (`res.users`). A table appears showing all users with their login and name columns. Typing in the search bar narrows the rows. Clicking a row opens the user's form.

**Acceptance Scenarios**:

1. **Given** a user navigates to a model's list view, **When** the page loads, **Then** records are displayed in a table with one row per record and one column per field.
2. **Given** the list view is showing records, **When** the user types in the search bar, **Then** the server is re-queried with a domain filter and only matching rows are shown.
3. **Given** records exist and pagination is needed, **When** the page loads, **Then** records are shown 50 per page with Previous/Next controls.
4. **Given** the list view, **When** the user clicks a row, **Then** the form view for that record opens.
5. **Given** the list view, **When** the user clicks "New", **Then** an empty form view opens for creating a record.

---

### User Story 4 — Form View (Priority: P3)

The user can view and edit a single record. All fields are displayed with their current values. Editable fields become input controls. The user can save changes, discard them, or delete the record.

**Why this priority**: CRUD completion — list view is useful for reading but form view is required to create and update data.

**Independent Test**: Open any user record, change the name field, click Save, navigate away and return — the new name persists. Click Discard instead — the original value is restored. Click Delete — the record is removed and the list view is shown.

**Acceptance Scenarios**:

1. **Given** a user opens a form view for an existing record, **When** the page loads, **Then** all fields are displayed with their current values.
2. **Given** a form view is open, **When** the user edits a field and clicks Save, **Then** the record is updated and a success message is shown.
3. **Given** a form view is open, **When** the user edits a field and clicks Discard, **Then** values revert to the last saved state without any server call.
4. **Given** a form view is open for an existing record, **When** the user clicks Delete and confirms, **Then** the record is removed and the user is taken back to the list view.
5. **Given** a form view for a new record, **When** the user fills required fields and clicks Save, **Then** the record is created and the form switches to edit mode showing the new ID.

---

### User Story 5 — Navigation (Priority: P3)

The user can always tell where they are. A breadcrumb trail shows the path (Home › Module › Model › Record). A sidebar or top navigation shows the models available within the current module. The browser Back button works as expected.

**Why this priority**: Without navigation context, users get lost. Breadcrumbs and browser history support are baseline usability requirements.

**Independent Test**: Navigate Home › base › res.users › record #1. The breadcrumb shows all four levels. Clicking "res.users" in the breadcrumb returns to the list. Pressing browser Back also returns to the list.

**Acceptance Scenarios**:

1. **Given** a user is on any screen, **When** they look at the breadcrumb, **Then** it shows the correct navigation path from Home to the current location.
2. **Given** a breadcrumb is visible, **When** the user clicks any segment, **Then** they are taken to that level.
3. **Given** a user is on any screen, **When** they look at the sidebar, **Then** they see a global list of all registered models they can navigate to.
4. **Given** a user navigated forward, **When** they press the browser Back button, **Then** they return to the previous screen without a full page reload.

---

### Edge Cases

- What happens when a model has no records? → List view shows "No records found" with a New button.
- What happens when a required field is left empty on save? → Inline validation error shown next to the field; save is blocked.
- What happens when the session expires mid-use? → The next API call returns an auth error; the user is redirected to the login page with a "Session expired" message.
- What happens when a model has many fields (>20)? → Form view groups them in sections; all fields remain accessible by scrolling.
- What happens when a field value is very long? → Text truncated in list view with ellipsis; shown in full in form view.
- What happens when the server is unreachable? → A banner error is shown; the user is not logged out.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The app MUST display a login screen as the entry point for unauthenticated users.
- **FR-002**: The app MUST store the session token in the browser and reuse it across page refreshes.
- **FR-003**: The app MUST redirect unauthenticated users to the login page when they attempt to access any other screen.
- **FR-004**: The home screen MUST display all installed modules as a navigable grid of tiles.
- **FR-005**: Each module tile MUST show the module name and a representative icon.
- **FR-006**: The list view MUST display all records of a model in a paginated table (50 records per page).
- **FR-007**: The list view MUST provide a search bar that filters records by re-fetching from the server with a domain filter on debounced input.
- **FR-008**: The list view MUST provide a "New" button that opens an empty form view.
- **FR-009**: The form view MUST display all fields of a record with their current values.
- **FR-010**: The form view MUST allow editing of non-readonly fields via appropriate input controls (text input, checkbox, number input, date picker).
- **FR-011**: The form view MUST provide Save, Discard, and Delete actions.
- **FR-012**: The form view MUST show inline validation errors for required fields before allowing save.
- **FR-013**: A breadcrumb trail MUST be visible on every screen except login, reflecting the full navigation path.
- **FR-014**: A sidebar MUST show a global list of all registered models, allowing navigation to any model's list view from any screen.
- **FR-015**: Browser navigation (Back/Forward) MUST work correctly using the URL hash (`window.location.hash`). See ADR-011 for the routing decision.
- **FR-016**: The app MUST work fully offline (no CDN dependencies; all assets served locally).
- **FR-017**: The app MUST communicate exclusively through the existing `/web/session/authenticate`, `/web/session/logout`, and `/jsonrpc` (execute_kw) endpoints.

### Key Entities

- **Session**: Token stored in browser; represents an authenticated user; has an expiry time.
- **Module**: An installed addon package with a name, version, and state; has an icon for display.
- **Model**: A registered ORM entity with a name and a set of fields; belongs to a module.
- **Record**: A single row of a model's data; has an integer ID and values for each field.
- **Field**: Metadata describing a model attribute — name, type (char, integer, boolean, date, many2one), required, readonly.

### Security Requirements

- **SEC-001**: Session token MUST be stored in `sessionStorage` (cleared on tab close) and never in a cookie or URL parameter.
- **SEC-002**: All data-modifying actions (save, delete) MUST include the session token in the request.
- **SEC-003**: The app MUST not expose the session token in page titles, breadcrumbs, or log output.
- **SEC-004**: The app MUST comply with OWASP Top 10; all user-supplied values displayed in the DOM MUST be escaped to prevent XSS.
- **SEC-005**: Delete action MUST require a confirmation dialog before sending the request.

### Performance Requirements

- **PERF-001**: Initial page load (login screen fully interactive) MUST complete in under 2 seconds on a local connection.
- **PERF-002**: Navigation between screens MUST feel instantaneous (under 300 ms for client-side transitions).
- **PERF-003**: List view with 50 records MUST render in under 500 ms after the API response is received.
- **PERF-004**: No known regressions permitted; page load and render benchmarks MUST run in CI.

### Accessibility Requirements

- **ACC-001**: All screens MUST meet WCAG 2.1 AA color contrast ratios (≥ 4.5:1 for normal text, ≥ 3:1 for large text).
- **ACC-002**: All interactive elements (buttons, inputs, links) MUST be keyboard-navigable with visible focus indicators.
- **ACC-003**: Error messages and state changes MUST be announced via ARIA live regions.
- **ACC-004**: Form inputs MUST have associated labels; icons used as buttons MUST have ARIA labels.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user can sign in, browse to any model, view a record, and log out within 60 seconds on first use.
- **SC-002**: The full application loads from a cold browser with no cached assets in under 2 seconds on localhost. (Validated by PERF-001 tooling.)
- **SC-003**: All primary user journeys (login → list → form → save/delete → logout) are covered by automated end-to-end tests.
- **SC-004**: Zero unhandled JavaScript errors occur during the primary user journeys in Chrome and Firefox.
- **SC-005**: All screens pass WCAG 2.1 AA accessibility checks with zero critical violations.
- **SC-006**: The app functions identically with the network tab blocked after initial asset load (no CDN calls).

## Assumptions

- The dodoo core server (Phase 1) is already running and fully operational with the `base` module installed.
- The `/web/core/info` endpoint (returns installed modules and registered models) is available.
- Only `admin` role users are expected in this milestone; fine-grained per-model access control is not in scope.
- Mobile responsiveness is a best-effort goal; the primary target is desktop browsers (1280px+).
- Only the following field types need UI support: Char, Integer, Boolean, Float, Date, Text, Many2one. One2many and Many2many are displayed as read-only counts in this milestone.
- Module icons are mapped from module name to a predefined set; custom icon upload is out of scope.
- The app is single-page (no server-side rendering); all routing is client-side.
- The `fields_get` JSON-RPC method is available on all models to retrieve field metadata.
