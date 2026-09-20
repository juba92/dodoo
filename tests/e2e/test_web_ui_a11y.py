"""Accessibility e2e tests using axe-playwright.

Requires:
    pip install axe-playwright
    playwright install chromium

Run:
    pytest tests/e2e/test_web_ui_a11y.py -v
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, sync_playwright

_BASE = "http://127.0.0.1:8069"
_CLIENT = f"{_BASE}/web/client"


@pytest.fixture(scope="session")
def a11y_browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture()
def a11y_page(a11y_browser):
    ctx = a11y_browser.new_context()
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: pytest.fail(f"Unhandled JS error: {e}"))
    yield pg
    pg.close()
    ctx.close()


def _login(page: Page) -> None:
    page.goto(_CLIENT)
    page.wait_for_selector("#f-login")
    page.fill("#f-login", "admin")
    page.fill("#f-password", "admin")
    page.click("button[type=submit]")
    # Not wait_for_url("**#/home"): the SPA's post-login redirect is a
    # same-document hash change with no 'load' lifecycle event, so
    # wait_for_url's default wait_until="load" never resolves and times out
    # even though the navigation already happened. Wait for the home
    # screen's own content instead.
    page.wait_for_selector(".module-tile")


def _run_axe(page: Page) -> list[dict]:
    """Inject axe-core and return violations."""
    page.add_script_tag(
        url="https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.9.0/axe.min.js"
    )
    results = page.evaluate("""
        () => new Promise(resolve =>
            axe.run({ runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } })
               .then(r => resolve(r.violations))
        )
    """)
    return results


def test_a11y_login(a11y_page: Page):
    a11y_page.goto(_CLIENT)
    a11y_page.wait_for_selector("#f-login")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        "WCAG 2.1 AA critical violations on login screen:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


def test_a11y_home(a11y_page: Page):
    _login(a11y_page)
    a11y_page.wait_for_selector(".module-tile")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        "WCAG 2.1 AA critical violations on home screen:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


def test_a11y_list(a11y_page: Page):
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/model/res.users")
    a11y_page.wait_for_selector("table")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        "WCAG 2.1 AA critical violations on list screen:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


def test_a11y_form(a11y_page: Page):
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/model/res.users/1")
    a11y_page.wait_for_selector(".form-card")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        "WCAG 2.1 AA critical violations on form screen:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


# 008-accounting-parity (ACC-001…003): four new screens — bank statements, lock
# exceptions, analytic accounts, tax report — same axe pass as the generic
# list/form/report screens above (zero WCAG 2.1 AA critical/serious violations).


def test_a11y_bank_statements_list(a11y_page: Page):
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/model/account.bank.statement")
    a11y_page.wait_for_selector("table, .empty-state")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        "WCAG 2.1 AA critical violations on bank statements list:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


def test_a11y_lock_exceptions_list(a11y_page: Page):
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/model/account.lock.exception")
    a11y_page.wait_for_selector("table, .empty-state")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        "WCAG 2.1 AA critical violations on lock exceptions list:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


def test_a11y_analytic_accounts_list(a11y_page: Page):
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/model/analytic.account")
    a11y_page.wait_for_selector("table, .empty-state")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        "WCAG 2.1 AA critical violations on analytic accounts list:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


def test_a11y_tax_report(a11y_page: Page):
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/accounting/reports/tax-report")
    a11y_page.wait_for_selector("table, .empty-state")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        "WCAG 2.1 AA critical violations on tax report screen:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


def test_a11y_lock_exception_active_status_is_text_not_color_only(a11y_page: Page):
    """ACC-003: `account.lock.exception`'s `active` field (the only status
    indicator on this screen — revoked exceptions are soft-deleted via
    `active=False`) must render as a visible text label ("Yes"/"No" per the
    generic list renderer's `_cellText`), not a color-only badge."""
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/model/account.lock.exception")
    a11y_page.wait_for_selector("table, .empty-state")
    headers = a11y_page.locator("table.data-table thead th")
    active_col = None
    for i in range(headers.count()):
        if headers.nth(i).inner_text().strip().lower() == "active":
            active_col = i
            break
    if active_col is None:
        pytest.skip("'active' column not present among the picked list columns")
    first_row_cells = a11y_page.locator("table.data-table tbody tr").first.locator("td")
    if first_row_cells.count() == 0 or "No records" in first_row_cells.first.inner_text():
        pytest.skip("no lock exceptions seeded")
    text = first_row_cells.nth(active_col).inner_text().strip()
    assert text in ("Yes", "No"), (
        f"active-status cell must carry a visible Yes/No text label, not color alone; got {text!r}"
    )


# 009-customer-database (ACC-001…003): customer list + form (including the
# AR-ledger panel) — same axe pass as the generic/008 screens above.


def test_a11y_customer_list(a11y_page: Page):
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/accounting/customers")
    a11y_page.wait_for_selector("table, .empty-state")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        "WCAG 2.1 AA critical violations on customer list:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


def test_a11y_customer_form_new(a11y_page: Page):
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/accounting/customer/new")
    a11y_page.wait_for_selector(".form-card")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        "WCAG 2.1 AA critical violations on new-customer form:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


def test_a11y_customer_list_rows_keyboard_reachable(a11y_page: Page):
    """ACC-002: customer-list.js's rows are its only way to open a record —
    same tabIndex=0 + Enter/Space pattern web/static/views/list.js already
    proves works, applied to this bespoke view (ADR-048)."""
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/accounting/customers")
    a11y_page.wait_for_selector("table.data-table")
    row = a11y_page.locator("table.data-table tbody tr").first
    # Language-independent empty-state check: the empty-state row is a single
    # colspan'd <td>, a real customer row has three (name/vat/balance) — a
    # hardcoded English-text check would silently mis-skip under Arabic mode.
    if row.count() == 0 or row.locator("td").count() < 3:
        pytest.skip("no customers seeded")
    assert row.get_attribute("tabindex") not in (None, "-1"), (
        "customer list rows must be in the tab order for keyboard operability"
    )


# 010-vendor-database (ACC-001…003): vendor list + form (including the
# AP-ledger panel) — same axe pass as the customer screens above.


def test_a11y_vendor_list(a11y_page: Page):
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/accounting/vendors")
    a11y_page.wait_for_selector("table, .empty-state")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        "WCAG 2.1 AA critical violations on vendor list:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


def test_a11y_vendor_form_new(a11y_page: Page):
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/accounting/vendor/new")
    a11y_page.wait_for_selector(".form-card")
    violations = _run_axe(a11y_page)
    critical = [v for v in violations if v.get("impact") in ("critical", "serious")]
    assert critical == [], (
        "WCAG 2.1 AA critical violations on new-vendor form:\n"
        + "\n".join(f"  [{v['id']}] {v['description']}" for v in critical)
    )


def test_a11y_vendor_list_rows_keyboard_reachable(a11y_page: Page):
    """ACC-002: vendor-list.js's rows are its only way to open a record — same
    tabIndex=0 + Enter/Space pattern customer-list.js already proves works,
    applied to this bespoke view (ADR-051)."""
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/accounting/vendors")
    a11y_page.wait_for_selector("table.data-table")
    row = a11y_page.locator("table.data-table tbody tr").first
    # Language-independent empty-state check: the empty-state row is a single
    # colspan'd <td>, a real vendor row has three (name/vat/balance) — a
    # hardcoded English-text check would silently mis-skip under Arabic mode.
    if row.count() == 0 or row.locator("td").count() < 3:
        pytest.skip("no vendors seeded")
    assert row.get_attribute("tabindex") not in (None, "-1"), (
        "vendor list rows must be in the tab order for keyboard operability"
    )


def test_a11y_list_rows_keyboard_reachable(a11y_page: Page):
    """ACC-002: every row-activation affordance on the four new screens must
    be operable without a pointer. This is a framework-level property of the
    shared generic list renderer (dodoo/addons/web/static/views/list.js),
    verified once here rather than per-screen since all four new screens
    (and every other model list) go through the same `<tr onclick=...>` code
    path with no feature-specific override."""
    _login(a11y_page)
    a11y_page.goto(f"{_CLIENT}#/model/account.bank.statement")
    a11y_page.wait_for_selector("table.data-table")
    row = a11y_page.locator("table.data-table tbody tr").first
    if row.count() == 0 or "No records" in row.inner_text():
        pytest.skip("no bank statements seeded")
    assert row.get_attribute("tabindex") not in (None, "-1"), (
        "list rows are the only way to open a record and must be in the tab "
        "order (tabindex must be set and not -1) for keyboard operability"
    )
