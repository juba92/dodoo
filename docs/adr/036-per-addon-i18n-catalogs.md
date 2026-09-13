# ADR-036: Per-Addon i18n Catalogs, Merged at Load Time

**Status**: Accepted
**Date**: 2026-09-13

## Context

Per ADR-019, dodoo's UI translation catalogs are static per-language JSON files
(`{source: translation}`) loaded once at import by `dodoo/addons/localization/i18n.py`, with
`translate()`/`fields_get`'s `_translate_label()` falling back EN → source string. Until this
change, `i18n.py` only ever loaded its **own** addon's catalog:
`dodoo/addons/localization/data/i18n/{lang}.json`. Every other addon's menu labels, section
titles, and field labels had to be added to that one central file by hand, in an addon the
feature's own code never touches.

In practice nobody did this for any addon after `localization` itself: grepping the 007-inventory
feature's new menu labels (`Warehouses`, `Barcode`, `Reordering Rules`, ...) and field labels
against the central catalog found none of them present, so with the UI language set to Arabic
the entire Inventory app rendered in English while every other app correctly showed Arabic. The
same grep against the existing `hr` and `fleet` addons found the identical gap — their own
menu/field labels (`Departments`, `Recruitment`, `Vehicles`, `Odometer`, ...) were never in the
central catalog either, meaning this bug has been present, silently, since those modules shipped
and was only masked by nobody testing them in Arabic. The user's report — "this happens every
time a new module is implemented" — was correct for `hr` and `fleet` as well as `stock`, not just
the module that surfaced it.

The root cause is structural, not a missing translation: the catalog file lives in an addon
(`localization`) that has no reason to know about strings introduced by addons that merely
happen to depend on it, the same way it has no reason to know their schema or seed data.

## Decision

Every addon now owns and ships its own translation catalog at
`dodoo/addons/<addon>/data/i18n/{lang}.json`, the same way it already owns `data/seed.py`,
`data/rules.py`, and `data/indexes.py`. `dodoo/addons/localization/i18n.py`'s `_load()` merges
**all** of them at import time:

1. `localization`'s own `data/i18n/*.json` first (generic web/base chrome and strings shared
   across addons with no single obvious owner).
2. Every other addon directory under `dodoo/addons/`, in a stable sorted order, that has a
   `data/i18n/` directory — discovered via `pathlib.Path(__file__).parent.parent` relative to
   `localization/i18n.py` (i.e. the `dodoo/addons/` directory every addon, including
   `localization`, lives in). No addon manifest declares this explicitly; it is filesystem
   convention, mirroring how `data/seed.py` etc. are discovered by installation order rather than
   manifest declaration.

Per language, a source string is `setdefault`-merged into the combined catalog: the first addon
(in the order above) to define a translation for a given source string wins. This makes
`localization`'s own definitions authoritative for shared/generic strings (`Name`, `Active`,
`Company`, ...) while still letting any addon supply its own definition for a string that is
otherwise undefined anywhere else.

`product/`, `stock/`, and `stock_account/` (007-inventory) now ship their own
`data/i18n/{en,ar}.json` covering their menu sections/items and field labels. `hr/` and `fleet/`
have been retrofitted with the same, closing the pre-existing gap discovered above.

## Rationale

The alternative — keep one central catalog file and simply remember to add every new addon's
strings to it — is exactly the process that already failed three times (`hr`, `fleet`, `stock`)
before this ADR, for the same reason ADR-035's checklist exists: an edit in a file the current
feature's diff has no structural reason to touch is easy to forget, and nothing fails loudly when
it's skipped (the string just silently falls back to English via `translate()`'s own designed
fallback, which is correct behavior for a genuinely missing translation but indistinguishable
from a forgotten one). Moving ownership to each addon's own directory makes the catalog a normal
part of "does this addon's `data/` look complete", visible in the same file listing as its schema
and seed data, and reviewable in the same diff that introduces the strings.

A database-backed translation model with an in-app editing screen (Odoo's approach) was
considered and rejected again here for the same reasons as ADR-007/ADR-019: it is materially more
machinery than dodoo's current static-JSON i18n needs, and does not by itself fix the "nobody
remembers to populate it for a new module" problem — it only changes where the missed entry lives.

## Consequences

- **Every future addon must ship `data/i18n/{en,ar}.json`** (or however many languages
  `available_langs()` needs to support) alongside its other `data/*.py` files, the moment it
  introduces any user-facing string not already defined by an addon it depends on (menu section
  names, menu item labels, field `string=` labels not covered by a generic term already in
  `localization`'s own catalog). Nothing in `localization/` ever needs to be edited again for a
  new addon's own strings.
- `/speckit-plan` and `/speckit-tasks` for any feature that introduces new UI-facing strings
  (menus, field labels, static screen text) MUST include a task to add or update that addon's own
  `data/i18n/{en,ar}.json`, the same way ADR-035 requires a task per its checklist item for new
  `application: true` modules.
- This ADR only fixes label-level translation (menu labels, field `string=` labels resolved via
  `_translate_label()` in `fields_get`). It does **not** fix translation of `Selection` field
  *values* (e.g. a stored `"draft"`/`"done"`/`"incoming"` enum value rendered raw in list/form
  views) — `fields_get` does not return per-choice labels and the client has no value-label
  resolution mechanism at all. That is a distinct, deeper gap, not addressed by this change.
- This retroactively fixes `hr` and `fleet`'s own long-standing missing-translation gap as a
  side effect of fixing the architecture, but does not by itself guarantee every string in every
  existing addon has been ported — only the menu and field labels enumerated from each addon's
  models/menus at the time this ADR was written. A future audit pass may still find gaps in
  screen-specific static text that isn't a field label or menu item.
- **`tests/localization/test_i18n_coverage.py` enforces this automatically now.** It imports
  every addon, walks `_ALL_MODELS` for every field's effective label (`field.string or
  _humanize(fname)` — the exact computation `fields_get` uses) and every `label`/`section` string
  in every addon's `static/*-menu.js`, and asserts each one is a key in the merged English *and*
  Arabic catalogs. A checklist item is easy to skip silently, as this ADR's own Context section
  demonstrates three times over; a failing test on a new addon's un-translated label is not. Any
  addon that introduces a new menu label or model field must add a catalog entry for it or this
  test fails — this is the actual guarantee, not just the process note above.
- Running that test against every existing addon at the time it was added also surfaced gaps this
  ADR's own initial audit missed: `stock_account.stock_valuation_layer.stock_move_id` ("Stock
  Move"), five `hr.resource_calendar` fields (day of week, work-hours range, timezone), a
  pre-existing gap in `account` predating this ADR (`credit_move_id`, `debit_move_id`, the
  `price_*` fields on `account.move.line`, `note`), and ~30 fields on `base`'s internal
  `ir.model`/`ir.model.field`/`ir.rule`/`ir.session`/`res.lang`/`res.groups` models that have no
  menu route today (translated anyway, matching Odoo's own Technical-menu labels, since `base` is
  the addon every future "Technical" settings screen would read from). All were added to the
  owning addon's own `data/i18n/{en,ar}.json` (a new `data/i18n/` for `account` and `base`, which
  previously had none) rather than to `localization`, per the Decision above.
