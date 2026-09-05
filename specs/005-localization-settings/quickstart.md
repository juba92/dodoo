# Quickstart: Localization & Settings — Validation Guide

Runnable checks proving the feature works end to end. Assumes the dodoo dev setup from `specs/003-accounting`
(PostgreSQL reachable via `DATABASE_URL` / `TEST_DATABASE_URL`).

## Prerequisites

```bash
pip install -e ".[dev]"
python -m playwright install chromium        # for the e2e checks
export DATABASE_URL=postgresql+asyncpg://dodoo:dodoo@127.0.0.1:5432/dodoo
```

## 1. Install the addon (fresh DB ⇒ Egypt + Arabic defaults)

```bash
python -m dodoo module install localization      # pulls in base, account, web
```

Expected: install logs show `seed res.lang (ar, en)`, `seed res.country (…)`,
`apply_country_localization EG`, `currency EGP seeded`, `archived generic 20% taxes`.

## 2. Automated test suite

```bash
pytest tests/unit/test_i18n.py tests/unit/test_localization_packs.py \
       tests/integration/test_localization_settings.py \
       tests/integration/test_country_localization.py \
       tests/integration/test_i18n_endpoint.py -v

pytest tests/e2e/test_localization_ui.py -v      # requires: python -m dodoo server --port 8069
```

All green. Coverage for `dodoo/addons/localization/` ≥ 80%; 100% branch coverage on
`i18n.translate`, `service.apply_country_localization`, the currency-conflict guard, and the
effective-language resolver.

## 3. Manual API checks (`curl`)

Authenticate and keep the token:

```bash
TOKEN=$(curl -s localhost:8069/web/session/authenticate -H 'Content-Type: application/json' \
  -d '{"login":"admin","password":"admin"}' | python -c 'import sys,json;print(json.load(sys.stdin)["session_token"])')
```

### 3a. Client catalog + direction (FR-007b, FR-009)

```bash
curl -s localhost:8069/web/i18n/ar.json | python -m json.tool | head -20
# → "direction": "rtl", "terms": { "Home": "الرئيسية", ... }
curl -s localhost:8069/web/i18n/en.json | python -m json.tool | head -8
# → "direction": "ltr"
curl -s -o /dev/null -w '%{http_code}\n' localhost:8069/web/i18n/fr.json   # → 400
```

### 3b. Read settings (contract: `res_config_settings.md`)

```bash
curl -s localhost:8069/jsonrpc -H "X-Session-Token: $TOKEN" -H 'Content-Type: application/json' -d '{
  "jsonrpc":"2.0","id":1,"method":"call","params":{"service":"object","method":"execute_kw",
  "args":["res.config.settings","get_values",[]],"kwargs":{}}}' | python -m json.tool
# → lang "ar", country_code "EG", tax_label "VAT", tax_rounding_method "round_globally",
#   available_langs [ar,en], company_write_date present
```

### 3c. Switch system language to English (FR-004)

```bash
WD=$(curl -s ... get_values ... | python -c 'import sys,json;print(json.load(sys.stdin)["result"]["company_write_date"])')
curl -s localhost:8069/jsonrpc -H "X-Session-Token: $TOKEN" -H 'Content-Type: application/json' -d "{
  \"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"call\",\"params\":{\"service\":\"object\",\"method\":\"execute_kw\",
  \"args\":[\"res.config.settings\",\"set_values\",[{\"lang\":\"en\",\"company_write_date\":\"$WD\"}]],\"kwargs\":{}}}" \
  | python -m json.tool
# → {"ok": true, ...}; a subsequent get_values shows lang "en"
```

Re-running the same call with the now-stale `$WD` returns `DodooError("settings_stale")` (FR-033).

### 3d. Personal language override (FR-005, FR-006)

```bash
curl -s ... execute_kw ["res.config.settings","set_user_lang",["ar"]] ...
# → {"ok": true, "effective_lang": "ar", "direction": "rtl"}
# even though the system default is now "en"; /web/core/info for this user shows lang "ar"
```

### 3e. Non-admin is refused (SEC-002/004)

Create a non-admin user, authenticate as them, call `set_values` → JSON-RPC error `-32000`,
`data.type = "AccessError"`. `set_user_lang` for their own row still succeeds.

## 4. Country change with existing posted data (FR-026, FR-028)

```bash
pytest tests/integration/test_country_localization.py::test_currency_conflict_blocks_without_confirm -v
```

The test: applies Egypt, posts a journal entry in EGP, then calls `set_values` with
`country_code="GB"` (GBP). First call → `{"ok": false, "warning": "currency_change_requires_confirmation",
"detail": {"from":"EGP","to":"GBP","posted_lines": >0}}` and **no** row changes. Second call with
`confirm_currency_change=true` → succeeds; the previously posted entry is byte-for-byte unchanged
(amounts, currency, taxes), and the Egypt taxes/fiscal positions still exist (archived, not deleted).

## 5. Manual UI walkthrough (optional)

1. `python -m dodoo server --port 8069`, open `http://127.0.0.1:8069/web/client`.
2. Fresh install → login page renders **right-to-left** in Arabic; `<html dir="rtl" lang="ar">`.
3. Log in → home, sidebar on the right, breadcrumb separators mirrored.
4. Navigate to **Settings** (`#/settings`) → set Language = English → save → UI reflows **left-to-right**
   in English on next render without re-login.
5. In Settings set Country = United Kingdom → save → no tax/currency change, tax label unchanged for
   already-posted docs; Country = Egypt again → EGP + VAT 14% defaults restored, no duplicate taxes.

## Success signals (map to spec Success Criteria)

| Check | Criterion |
|-------|-----------|
| Step 3a + UI step 2/3 | SC-001, SC-002 |
| Step 3d | SC-003 |
| Step 1 + `test_country_localization` fresh-install case | SC-004 |
| `test_country_localization` apply timing assertion (< 3 s) | SC-005 |
| Step 4 re-apply / switch-back invariants | SC-006, SC-007 |
| Step 4 first call | SC-008 |
| e2e formatter assertions | SC-009 |
| `test_localization_settings` user-create case | SC-010 |
