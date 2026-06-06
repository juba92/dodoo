# Tasks: Dodoo Web UI

**Input**: Design documents from `/specs/002-web-ui/`

**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/api-consumed.md ✓, quickstart.md ✓

**Analysis**: All 12 findings from `/speckit-analyze` resolved (2 CRITICAL, 1 HIGH, 6 MEDIUM, 3 LOW).

**Tests**: Playwright e2e tests included (requested in plan.md). Integration test for static serving included.

**Organization**: Tasks grouped by phase matching the 7 implementation phases in plan.md. User story phases are independently testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)

---

## Phase 1: Addon Scaffold + Static Serving

**Purpose**: Create the `web` addon package, mount static files, and confirm the server delivers `index.html` at `/web/client`.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 Create addon directory tree: `dodoo/addons/web/`, `dodoo/addons/web/http/`, `dodoo/addons/web/static/`, `dodoo/addons/web/static/views/`
- [X] T002 [P] Create `dodoo/addons/web/__manifest__.py` with `{"name": "Web Client", "version": "1.0.0", "depends": ["base"]}`
- [X] T003 [P] Create `dodoo/addons/web/__init__.py` with empty `async def post_install(env): pass`
- [X] T004 Create `dodoo/addons/web/http/__init__.py`: mount `StaticFiles` at `/web/static/` from the addon's `static/` directory; register `GET /web/client` that returns `index.html`
- [X] T005 [P] Create `dodoo/addons/web/static/index.html`: minimal SPA shell that imports `app.js` as `type="module"` and contains `<div id="app"></div>` and an ARIA live region `<div aria-live="polite" id="status"></div>`
- [X] T006 [P] Create `dodoo/addons/web/static/style.css`: CSS reset, CSS variables for color/spacing, base layout (header + sidebar + main), focus-visible ring, and `.sr-only` utility class
- [X] T007 Create `tests/integration/test_web_serving.py`: pytest-asyncio tests asserting HTTP 200 for `GET /web/client`, `GET /web/static/app.js`, `GET /web/static/style.css`, and `GET /web/static/views/login.js`
- [X] T008 [P] Write ADR `docs/adr/011-hash-routing.md`: document decision to use hash-based routing instead of History API, rationale (no server catch-all needed), and alternatives considered
- [X] T009 [P] Write ADR `docs/adr/012-vanilla-js-spa.md`: document decision to use vanilla JS ES2022 modules with no bundler, rationale (no build step, offline-capable, evergreen browsers), and alternatives considered
- [X] T010 [P] Write ADR `docs/adr/013-static-files-addon.md`: document decision to serve static files via `StaticFiles` mount inside the addon's `http/__init__.py`, rationale (self-contained, uses bundled Starlette), and alternatives considered

**Checkpoint**: `GET /web/client` returns 200 with `index.html` content. Integration test passes.

---

## Phase 2: Core JS — api.js + app.js Router

**Purpose**: Build the shared JavaScript foundation that all views depend on. Foundational — no view can work without this.

**⚠️ CRITICAL**: All user story phases depend on this phase completing first.

- [X] T011 Create `dodoo/addons/web/static/api.js`: export `authenticate(login, password)` (POST `/web/session/authenticate`), `logout()` (POST `/web/session/logout`), `rpc(model, method, args, kwargs)` (POST `/jsonrpc` with `execute_kw`), `getInfo()` (GET `/web/core/info`); read/write session token via `sessionStorage`; inject `X-Session-Token` header on every request; intercept JSON-RPC error code `-32000` and navigate to `#/login?reason=expired`
- [X] T012 Create `dodoo/addons/web/static/app.js`: define `App.state = {token, uid, modules, models, fieldCache}`; implement `App.navigate(hash)` to push hash; implement hash router listening on `hashchange` and `load` events that matches route patterns (`#/login`, `#/home`, `#/module/:name`, `#/model/:name`, `#/model/:name/new`, `#/model/:name/:id`) and dynamically imports the correct view module; render layout shell (semantic `<header>` with app name + logout button, `<nav>` sidebar placeholder, `<main id="main">` content area, `<nav aria-label="breadcrumb">` breadcrumb strip); redirect unauthenticated users to `#/login`; bootstrap on DOMContentLoaded by reading token from `sessionStorage` and routing to current hash

**Checkpoint**: Opening `/web/client#/login` in a browser shows the login route is active (even without view content). Console has no errors. Hash changes are handled.

---

## Phase 3: US1 — Login Screen (Priority: P1) 🎯 MVP

**Goal**: Users can authenticate with login/password, session token is stored, and invalid credentials show an error message.

**Independent Test**: Navigate to `/web/client` without a session → login page appears. Submit wrong credentials → error shown. Submit correct credentials → redirected to `#/home`. Refresh → stay on home.

### E2E Tests for US1

- [X] T013 [US1] Create `tests/e2e/test_web_ui.py`: add pytest fixtures for Playwright browser, server URL (`http://127.0.0.1:8069`), and page setup; in the page fixture attach `page.on("pageerror", lambda e: pytest.fail(f"Unhandled JS error: {e}"))` to catch unhandled JS exceptions (satisfies SC-004, Constitution IX); write `test_us1_login_success` (admin/admin → redirect to `#/home`), `test_us1_login_failure` (wrong password → error message visible, stay on `#/login`), `test_us1_session_persist` (login → refresh → still on `#/home`, not redirected), `test_us1_logout` (click logout → redirected to `#/login`, token cleared)

### Implementation for US1

- [X] T014 [US1] Create `dodoo/addons/web/static/views/login.js`: export `render(container)` that builds a `<form>` with labeled `<input type="text" id="login">`, `<input type="password" id="password">`, and `<button type="submit">Sign In</button>`; on submit call `api.authenticate()`, store token + uid in `App.state` and `sessionStorage`, navigate to `#/home`; on 401 display inline error message using `element.textContent` (no innerHTML with API data); if session token already exists in App.state on render, immediately navigate to `#/home`; read `?reason=expired` from query string and show "Session expired" banner if present

**Checkpoint**: All 4 US1 e2e tests pass. Login flow is fully functional.

---

## Phase 4: US2 — Home Screen (Priority: P2)

**Goal**: After login, users see a grid of installed module tiles with names and icons. Clicking a tile navigates to that module.

**Independent Test**: Navigate to `#/home` after login → at least one tile (`base`) shown with name and icon. Click tile → navigate to `#/module/base`.

### E2E Tests for US2

- [X] T015 [US2] Add US2 tests to `tests/e2e/test_web_ui.py`: `test_us2_home_shows_tiles` (login → `#/home` → at least one module tile visible), `test_us2_tile_has_name_and_icon` (tile shows text label and icon element), `test_us2_tile_click_navigates` (click `base` tile → URL hash changes to `#/module/base`)

### Implementation for US2

- [X] T016 [US2] Create `dodoo/addons/web/static/views/home.js`: export `render(container)` that calls `api.getInfo()` and stores result in `App.state.modules` and `App.state.models`; render a `<section>` with a heading and a CSS grid of module cards; each card is a `<button>` with an icon (emoji or CSS class mapped from module name) and a `<span>` label set via `textContent`; clicking a card calls `App.navigate('#/module/' + module.name)`; show loading state while fetching; show error message if fetch fails

**Checkpoint**: US2 e2e tests pass. Module tiles visible after login. Prior US1 tests still pass.

---

## Phase 5: US3 — List View (Priority: P2)

**Goal**: Any registered model can be browsed as a paginated table with a search bar, column headers, and a "New" button.

**Independent Test**: Navigate to `#/model/res.users` → table renders with at least one row. Search `admin` → filtered to one row. Click "New" → navigates to `#/model/res.users/new`.

### E2E Tests for US3

- [X] T017 [US3] Add US3 tests to `tests/e2e/test_web_ui.py`: `test_us3_list_renders_table` (`#/model/res.users` → `<table>` with `<thead>` and `<tbody>` rows), `test_us3_search_filters_rows` (type `admin` in search → only matching row visible), `test_us3_new_button_navigates` (click "New" → hash changes to `#/model/res.users/new`), `test_us3_row_click_navigates` (click first row → hash changes to `#/model/res.users/1`)

### Implementation for US3

- [X] T018 [US3] Create `dodoo/addons/web/static/views/list.js`: export `render(container, params)` where `params.model` is the model name; call `api.rpc(model, 'fields_get', [], {attributes: ['string','type','required','readonly','relation']})` on first visit and cache in `App.state.fieldCache`; call `api.rpc(model, 'search_read', [[]], {fields: charAndIntFields, limit: 50, offset: 0})` to get records; render `<table>` with `<thead>` (column headers from `fields_get`) and `<tbody>` (rows with `textContent`-set cells); add search `<input>` that re-fetches with domain filter on debounced input; add "Next"/"Prev" pagination buttons that adjust `offset`; add "New" `<button>` that navigates to `#/model/${model}/new`; clicking a row navigates to `#/model/${model}/${row.id}`; all API data set via `textContent` (never `innerHTML`)

**Checkpoint**: US3 e2e tests pass. List view renders for any model. Prior US1+US2 tests still pass.

---

## Phase 6: US4 — Form View (Priority: P3)

**Goal**: Users can view and edit a single record with field controls appropriate to each field type. Save persists, Discard restores, Delete removes after confirmation.

**Independent Test**: Navigate to `#/model/res.users/1` → all fields shown with values. Change `name` → Save → value persists on refresh. Discard → original value restored. Navigate to `#/model/res.users/new` → empty form → fill login/name → Save → new record created, URL updates to new ID.

### E2E Tests for US4

- [X] T019 [US4] Add US4 tests to `tests/e2e/test_web_ui.py`: `test_us4_form_loads_record` (`#/model/res.users/1` → login field shows `admin`), `test_us4_save_persists` (change name → Save → refresh → updated name), `test_us4_discard_restores` (change name → Discard → original value back, no server call), `test_us4_delete_requires_confirm` (click Delete → `window.confirm` dialog → cancel → record still exists), `test_us4_create_new_record` (`#/model/res.users/new` → fill login+name → Save → URL changes to new record ID)

### Implementation for US4

- [X] T020 [US4] Create `dodoo/addons/web/static/views/form.js`: export `render(container, params)` where `params.model` and `params.id` (or `'new'`); for existing records call `api.rpc(model, 'read', [[id]], {fields})` and snapshot `originalValues`; render a `<form>` with field controls by type — `char`/`text` → `<input type="text">` or `<textarea>`, `integer`/`float` → `<input type="number">`, `boolean` → `<input type="checkbox">`, `date` → `<input type="date">`, `many2one` → `<input type="number">` (ID) with label showing relation name; readonly fields rendered as `<span>` not `<input>`; for models with >20 fields, group every 10 fields into a `<fieldset>` with a sequential legend ("Fields 1–10", "Fields 11–20", etc.) so all fields remain accessible by scrolling; track dirty state on `change` events; Save button — if new record: `create` call, then navigate to `#/model/${model}/${newId}`; if existing: `write` call, show success, refresh values; Discard button — restore from `originalValues` snapshot without server round-trip; Delete button — `window.confirm()` required, then `unlink` call, then navigate to list; validate required fields before save and show inline error messages; all API strings set via `textContent`

**Checkpoint**: US4 e2e tests pass. Full CRUD cycle works. Prior US1+US2+US3 tests still pass.

---

## Phase 7: US5 — Navigation + Polish + CI (Priority: P3)

**Goal**: Breadcrumb trail tracks user's path through the app. Sidebar lists models. Keyboard navigation works. App is accessible and CI runs e2e tests.

**Independent Test**: Navigate Home → base → res.users → record #1 → breadcrumb shows 4 segments. Click `res.users` in breadcrumb → back to list. Browser Back → correct screen. Zero axe WCAG 2.1 AA violations on all 4 screens.

### E2E Tests for US5

- [X] T021 [US5] Add US5 tests to `tests/e2e/test_web_ui.py`: `test_us5_breadcrumb_trail` (login → home → module → list → form → breadcrumb has 4 segments with correct labels), `test_us5_breadcrumb_click_navigates` (click list segment in breadcrumb → back to list view), `test_us5_back_button` (navigate forward then browser back → correct screen restored), `test_us5_sidebar_shows_models` (home screen → sidebar lists model names from `App.state.models`)
- [X] T022 [P] [US5] Create `tests/e2e/test_web_ui_a11y.py`: import `axe_playwright`; write `test_a11y_login`, `test_a11y_home`, `test_a11y_list`, `test_a11y_form` — each navigates to the screen and runs `axe.run()`, asserting zero critical WCAG 2.1 AA violations

### Implementation for US5

- [X] T023 [US5] Update `dodoo/addons/web/static/app.js`: add `App.breadcrumb = []` array tracking `{label, hash}` entries; push entry on `App.navigate()`; pop entries when navigating back (detect by checking if target hash already exists in breadcrumb); render breadcrumb in `<nav aria-label="breadcrumb">` as `<ol>` with `<li>` items — clickable segments as `<button>`, current segment as `<span aria-current="page">`; populate sidebar `<nav>` with the **global** model list from `App.state.models` as `<ul><li><button>` items that navigate to `#/model/:name` (sidebar is always all registered models, not scoped to current module — resolves FR-014)
- [X] T024 [P] [US5] Polish `dodoo/addons/web/static/style.css`: add full Odoo-inspired theme (top navigation bar with logo area and user info, sidebar with model list, main content area with card-style panels, table styles with alternating rows and `overflow: hidden; text-overflow: ellipsis; white-space: nowrap` on `<td>` cells to truncate long values, form layout with two-column field grid, button variants: primary/secondary/danger, responsive breakpoints for narrow screens, focus-visible outline in brand color, `.sr-only` for screen-reader-only text)
- [X] T025 [P] Add `playwright` to `pyproject.toml` under `[project.optional-dependencies]` `dev` group; document install command `pip install -e ".[dev]" && playwright install chromium firefox` in project README or quickstart
- [X] T026 Create or update `.github/workflows/ci.yml`: add `e2e` job with `services.postgres` (PostgreSQL 15), steps to install python deps + `playwright install --with-deps chromium firefox`, start dodoo server as background process, wait for health check, run `pip-audit` to check Python deps for CVEs (blocks on HIGH/CRITICAL findings — Constitution VII), run `pytest tests/e2e/ -v` (Chromium), run `pytest tests/e2e/ -v --browser firefox` (Firefox — satisfies SC-004), upload Playwright trace on failure as artifact

**Checkpoint**: All US5 e2e tests pass. Axe reports zero critical violations. CI e2e job runs green. All prior US1–US4 tests still pass.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final hardening across all user stories.

- [X] T027 [P] Security review: audit all JS files to confirm no `innerHTML` is used with API-returned data; verify `esc()` utility HTML-encodes structural template strings; verify `X-Session-Token` is never logged or exposed in URLs
- [X] T028 [P] Performance verification: manually open browser DevTools and confirm initial load of `/web/client` is under 2 seconds; automated timing assertions run via T033 in CI — this task verifies the dev environment matches CI results
- [X] T029 [P] Dependency audit: confirm `playwright` is the only new dev dependency; confirm all JS files have zero external CDN calls; confirm `static/` directory works fully offline after first page load; run `pip-audit` locally to confirm no HIGH/CRITICAL CVEs in new deps
- [X] T030 Run integration tests `pytest tests/integration/test_web_serving.py -v` and confirm 100% pass; run e2e suite `pytest tests/e2e/ -v` end-to-end with live server; confirm no test bypasses (`skip`, `xfail`) are present without justification
- [X] T031 [P] Run `ruff check dodoo/addons/web/` and fix any linting violations in Python addon files
- [X] T032 Create `dodoo/addons/web/static/tests/api.test.js`: JS unit tests using Node.js built-in `node:test` runner (no new dependency) covering `api.js` logic — mock `fetch` and `sessionStorage` using `node:test` mocks; test cases: (1) `authenticate()` stores token in sessionStorage on 200 response, (2) `authenticate()` throws on 401, (3) `rpc()` injects `X-Session-Token` header from sessionStorage, (4) `rpc()` navigates to `#/login?reason=expired` on JSON-RPC error code `-32000`, (5) `logout()` clears sessionStorage; add `"test:js": "node --test static/tests/api.test.js"` script to `pyproject.toml` or document as `node --test dodoo/addons/web/static/tests/api.test.js`; add this step to T026's CI job after the server starts
- [X] T033 [P] Add Playwright timing assertions to `tests/e2e/test_web_ui.py` for automated CI benchmark (Constitution IV + PERF-001/002/003): in `test_us1_login_success` measure time from page load to login form interactive and assert < 2000ms; in `test_us2_home_shows_tiles` measure hash navigation from `#/login` to `#/home` and assert < 300ms; in `test_us3_list_renders_table` measure time from navigation to first `<tbody><tr>` visible and assert < 500ms; use `time.monotonic()` around Playwright `wait_for_selector` calls

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundation)**: Depends on Phase 1 — BLOCKS all user story phases
- **Phase 3 (US1)**: Depends on Phase 2 — Can start once foundation is complete
- **Phase 4 (US2)**: Depends on Phase 2 — Can start once foundation is complete
- **Phase 5 (US3)**: Depends on Phase 2 — Can start once foundation is complete
- **Phase 6 (US4)**: Depends on Phase 2 — Can start once foundation is complete
- **Phase 7 (US5)**: Depends on Phases 3, 4, 5, 6 (needs all views to exist before breadcrumb/sidebar can be wired)
- **Phase 8 (Polish)**: Depends on Phase 7 completion

### User Story Dependencies

- **US1 (P1 — Login)**: Independent after Phase 2 — no dependency on other stories
- **US2 (P2 — Home)**: Independent after Phase 2 — uses `api.getInfo()` only
- **US3 (P2 — List)**: Independent after Phase 2 — uses `api.rpc()` only
- **US4 (P3 — Form)**: Independent after Phase 2 — uses `api.rpc()` only
- **US5 (P3 — Navigation)**: Depends on US1–US4 being complete (breadcrumb wires all views together)

### Within Each Phase

- E2E tests must be written before implementation (TDD for browser tests)
- Tasks marked [P] within a phase can run in parallel
- Sequential tasks within a phase must run in order

---

## Parallel Opportunities

```bash
# Phase 1 — run in parallel:
T002  # __manifest__.py
T003  # __init__.py
T005  # index.html
T006  # style.css
T008  # ADR 011
T009  # ADR 012
T010  # ADR 013

# Phase 3+4+5+6 — can run in parallel once Phase 2 is done:
# Developer A: T013, T014  (US1 Login)
# Developer B: T015, T016  (US2 Home)
# Developer C: T017, T018  (US3 List)
# Developer D: T019, T020  (US4 Form)

# Phase 8 — run in parallel:
T027  # security review
T028  # performance verification (manual)
T029  # dependency audit + pip-audit
T031  # ruff lint
T032  # JS unit tests for api.js
T033  # Playwright timing assertions (automated perf CI)
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Addon scaffold
2. Complete Phase 2: api.js + app.js foundation
3. Complete Phase 3: US1 Login
4. **STOP and VALIDATE**: Run `pytest tests/e2e/test_web_ui.py::test_us1_login_success -v`
5. If green: install `web` addon, start server, open `/web/client` in browser

### Incremental Delivery

1. Phase 1 + Phase 2 → Serving layer ready
2. Phase 3 → Login works → MVP shipped
3. Phase 4 → Home screen with modules → Demo-able
4. Phase 5 → List view → Browse data
5. Phase 6 → Form view → Edit data
6. Phase 7 → Navigation polish + CI → Production-grade
7. Phase 8 → Security/perf hardening → Done

### Install the Addon During Development

```bash
source .venv/bin/activate
set -a && source .env && set +a
python -m dodoo module install web
python -m dodoo server --port 8069
# Then open http://127.0.0.1:8069/web/client
```

---

## Notes

- [P] tasks = different files, no dependencies on incomplete sibling tasks
- [USn] label maps each task to a specific user story for traceability
- Each user story phase is independently completable and testable
- All API data inserted into DOM MUST use `textContent` — never `innerHTML` with API values
- All fetch calls MUST go through `api.js` — no inline `fetch()` in view files
- `fieldCache` MUST be populated once per model (cache in `App.state.fieldCache`)
- Discard MUST restore from `originalValues` — no server round-trip
- Delete MUST call `window.confirm()` before `unlink`
- Readonly fields MUST render as `<span>`, not `<input>`
