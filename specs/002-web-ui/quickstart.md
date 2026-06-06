# Quickstart: Dodoo Web UI

## Prerequisites

- dodoo core server running with `base` module installed (see `specs/001-erp-core/quickstart.md`)
- Server accessible at `http://127.0.0.1:8069`
- `playwright` installed: `pip install playwright && playwright install chromium`

## Install the Web Addon

```bash
source .venv/bin/activate
set -a && source .env && set +a
python -m dodoo module install web
```

Expected output:
```
INFO  Created table ... (none — no new tables)
INFO  Installed module 'web' version 1.0.0
Module 'web' installed successfully.
```

## Start the Server

```bash
python -m dodoo server --port 8069
```

## Validate: US1 — Login

Open `http://127.0.0.1:8069/web/client` in a browser.

**Expected**: Login page with two fields (Login, Password) and a Sign In button.

1. Enter `admin` / `admin` → click Sign In
2. **Expected**: Redirect to `http://127.0.0.1:8069/web/client#/home`
3. Refresh the page → **Expected**: Stay on home screen (session persisted)
4. Enter wrong password → **Expected**: Error message, stay on login page

## Validate: US2 — Home Screen

After login, verify:
- At least one module tile is shown (`base`)
- Each tile shows a name and icon
- Clicking the `base` tile navigates to `#/module/base`

## Validate: US3 — List View

1. Navigate to `#/model/res.users`
2. **Expected**: Table with columns for `login`, `name`, and other fields
3. Type `admin` in the search bar → **Expected**: Only the admin row shown
4. Click "New" → **Expected**: Empty form view opens at `#/model/res.users/new`

## Validate: US4 — Form View

1. From the list view, click the `admin` row → navigates to `#/model/res.users/1`
2. **Expected**: All fields shown with current values
3. Change the `name` field → click Save → **Expected**: Success message; value persists on refresh
4. Click Discard → **Expected**: Original value restored without any save
5. Create a new user: navigate to `#/model/res.users/new`, fill `login` and `name`, click Save
6. **Expected**: New record created; form switches to edit mode with the new ID in the URL

## Validate: US5 — Navigation

1. Navigate: Home → base → res.users → record #1
2. **Expected**: Breadcrumb shows `Home › base › res.users › #1`
3. Click `res.users` in breadcrumb → **Expected**: Back to list view
4. Press browser Back → **Expected**: Returns to previous screen correctly

## Validate: Logout

1. Click the Logout button in the navigation
2. **Expected**: Session cleared; redirect to `#/login`
3. Attempt to navigate to `#/home` directly → **Expected**: Redirected to `#/login`

## Validate: Offline Assets

1. Open browser DevTools → Network tab → check "Offline" (or throttle to "No throttle" after load)
2. Navigate between screens
3. **Expected**: All UI transitions work; only API calls fail (not asset loads)

## Run Automated E2E Tests

```bash
pytest tests/e2e/test_web_ui.py -v
```

All scenarios above must pass as automated tests.

## Validate: Accessibility

```bash
# Install axe-playwright or use browser axe extension
pytest tests/e2e/test_web_ui_a11y.py -v
```

Expected: Zero critical WCAG 2.1 AA violations on login, home, list, and form screens.
