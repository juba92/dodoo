# ADR-019: In-memory static JSON translation catalogs

**Status**: Accepted | **Date**: 2026-09-05

## Context

The feature translates only static UI strings for two fixed languages (ar, en). Options: an
`ir.translation`-style DB model (Odoo), gettext `.po` files with compilation, or static data files.

## Decision

Ship `dodoo/addons/localization/data/i18n/{ar,en}.json` (`{source: translation}`) parsed once at
addon import into a module dict. `translate(text, lang)` returns the value, falling back to the
English source, then to the key itself. No DB table, no translation-editing UI. A dedicated
`GET /web/i18n/{lang}.json` endpoint serves the catalog + locale metadata to the SPA, which caches
it in `sessionStorage`.

## Consequences

- Catalogs version with the code; missing-translation behaviour (English-source fallback) is trivial.
- Zero new dependencies, no build step.
- Business data is never translated — only the shipped UI-string catalogs.
- Rejected: `ir.translation` DB model (unjustified scope for two languages); gettext `.po` + `msgfmt`
  (new tooling, violates the dependency-hygiene principle).
