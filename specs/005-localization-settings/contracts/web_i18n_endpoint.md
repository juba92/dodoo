# Contract: `GET /web/i18n/{lang}.json`

Public REST route registered by the `localization` addon
(`@route("/web/i18n/{lang}.json", methods=["GET"], auth="public")`). Serves the client-string catalog and
locale metadata the SPA loads at bootstrap and on language change (FR-007b, ADR-007).

## Request

```
GET /web/i18n/ar.json
GET /web/i18n/en.json
```

`{lang}` is validated against active `res_lang.code`.

## Response — 200

```json
{
  "lang": "ar",
  "direction": "rtl",
  "name": "العربية",
  "date_format": "%d/%m/%Y",
  "decimal_point": ".",
  "thousands_sep": ",",
  "grouping": [3, 0],
  "terms": {
    "Home": "الرئيسية",
    "Save": "حفظ",
    "Discard": "تجاهل",
    "Login": "تسجيل الدخول",
    "Settings": "الإعدادات",
    "Country": "الدولة",
    "Language": "اللغة",
    "Customer Invoices": "فواتير العملاء",
    "Trial Balance": "ميزان المراجعة"
  }
}
```

- `terms` is the full flat catalog for `{lang}` (English source string → translation). Keys missing from
  `ar.json` are **omitted** here; the client's `t()` falls back to the key (which is the English source).
- `grouping` is emitted as a parsed JSON array (server parses the `res_lang.grouping` string).
- Response is cacheable per language; the client stores it in `sessionStorage` under `i18n:<lang>` and
  re-fetches only when the effective language changes.

## Response — 400 (unknown / inactive language)

```json
{ "error": "unknown_language", "detail": "no active res.lang with code 'fr'" }
```

## Response — 503

Standard degraded-DB response if `res_lang` cannot be read (mirrors `/web/health`).

## Related change: `GET /web/core/info`

Extended (additive) so the SPA learns the session user's effective language in the same bootstrap call it
already makes:

```json
{
  "modules": [ "..." ],
  "models": [ "..." ],
  "users": 1,
  "groups": 1,
  "lang": "ar",
  "direction": "rtl",
  "is_admin": true
}
```

`lang` / `direction` reflect the effective language for the caller (anonymous ⇒ system default).
`is_admin` lets the SPA decide whether to render the Settings mutation controls.
