# ADR-035: New Application-Module Registration Checklist

**Status**: Accepted
**Date**: 2026-09-13

## Context

`dodoo/addons/web/static/app.js` (and `views/home.js`) has no generic, metadata-driven
mechanism for registering a new top-level application module (`application: true` in its
manifest — e.g. `account`, `hr`, `fleet`, `stock`). Every such module's app tile, sidebar menu,
hash routing, breadcrumb labels, and multi-company/group state are wired by **hand-editing a
fixed set of hardcoded lookup tables and dispatch branches** spread across two files. This is a
direct, deliberate consequence of ADR-011 (hash routing) and ADR-012 (no bundler, no framework):
there is no router-config file or plugin-registration API to extend, only plain JS objects and
`if`/`switch` chains.

The 007-inventory feature (the `stock` app) shipped with several of these spots updated and
several forgotten. The observed symptom: opening the "Inventory" app tile fell through to the
generic "browse every model in this module" screen, which — because that screen's own model
filter was *also* a no-op bug — rendered every model in the entire system (starting
alphabetically with `account.*`) in both the main window and the sidebar. Tracing it required
walking the full click path (tile → `home.js` → `app.js`) by hand.

This has now happened for a new top-level module (following `hr`/`fleet` before it, per user
report of "every time"). The fix is this checklist, made mandatory for every future
`application: true` module, plus (see Consequences) hardening the fallback screen itself so a
*forgotten* entry degrades to "this app's models" instead of "every model in the system".

## Decision

Every time a new `application: true` addon is added, **all** of the following must be updated in
the same change — grep for an existing app's name (`hr`, `fleet`, or `stock`) across
`dodoo/addons/web/static/` to find every one of these spots mechanically; do not rely on memory:

1. **`dodoo/addons/<name>/static/<name>-menu.js`** — export the menu array
   (`export const <NAME>_MENU = [{section, requires, items: [{label, hash}]}]`), mirroring
   `hr-menu.js`/`stock-menu.js`. Every `hash` must be prefixed with the app's own hash prefix
   (`#/<prefix>/...`), never a bare `#/model/...`.

2. **`dodoo/addons/web/static/app.js`**:
   - `_render<Name>Menu(sidebar, currentHash)` + `_<name>Has(requires)` — copy
     `_renderStockMenu`/`_stockHas` (or `_renderHrMenu`/`_hrHas`) verbatim, swapping the menu
     import path and the `App.state.<name>Groups` field name.
   - `_renderSidebar`: add `if (hash.startsWith('#/<prefix>')) { ...; _render<Name>Menu(...); return; }`
     **before** the generic "Models" fallback block at the bottom of the function.
   - The navbar app-name `appNameEl.textContent = hash.startsWith(...) ? t('...') : ...` switch.
   - `modelRouteBase()`'s regex: add `<prefix>` to the `(accounting|hr|fleet|inventory|...)`
     alternation — otherwise every "open a record" / "create new" link from inside the app
     silently drops the user back into the generic `#/model/...` section.
   - `_ROUTES`: add `#/<prefix>/model/([^/]+)(/new|/(\d+))?` entries pointing at the existing
     generic `form.js`/`list.js` views (no new view file needed for plain CRUD screens — only
     add a bespoke view file for something the generic ones can't do, e.g. a kanban grouping or
     a bulk-edit sheet).
   - `_paramsFromHash`: add the **matching** parse entries for those same three route shapes.
     `_ROUTES` and `_paramsFromHash` are two independently-maintained lists for the same route
     set — adding to one and not the other (as happened here) produces a route that resolves to
     a view but renders it with no `model` param.
   - `_labelFromHash`: add the three `#/<prefix>/model/...` breadcrumb-label entries (copy the
     `#/hr/model/...` block), and add `<prefix>` to `_SECTION_MODEL_PREFIXES` in `_modelLabel` so
     `<prefix>.foo_bar` humanizes to "Foo Bar" instead of "<Prefix> Foo Bar". Add dedicated
     `_MODEL_LABELS` overrides for any model name that doesn't humanize well on its own.
   - `reloadLanguage()` **and** the second copy of the same login-info handling further down the
     file (there are two, kept in sync by hand) — both must read the new
     `App.state.<name>Groups = info.<name>_groups ?? []` field.

3. **`dodoo/addons/base/http/__init__.py`**'s `/web/core/info` route — add
   `<name>_groups: list[str]` (or an equivalent boolean flag for a single-group module like
   Fleet's `fleet_manager`) to both the local variable block and the returned `JSONResponse` dict,
   following the exact `hr_groups`/`stock_groups` pattern.

4. **`dodoo/addons/web/static/views/home.js`** — **all four** of:
   - `_MODULE_ICONS[name]`
   - `_MODULE_DISPLAY_NAMES[name]`
   - `_MODULE_COLORS[name]`
   - **`_MODULE_HOME_ROUTE[name]`** — the one actually missing this time. Point it at the app's
     own landing hash (`#/<prefix>/...`), never left unset "for later".

None of steps 1–4 has a compiler, type system, or test that fails when skipped — the app tile
still renders, still has an icon, and still "opens something". Only step 4's
`_MODULE_HOME_ROUTE` entry (or its absence) determines whether it opens the real app or the raw
fallback. That silence is exactly why this needs a checklist rather than relying on the symptom
to surface loudly.

## Rationale

A generic manifest-driven menu/route registry would remove the need for this checklist entirely,
but that is a materially larger change (a real router config format, a menu-contribution API
addons register into at install time, dynamic breadcrumb-label resolution from `fields_get`
instead of hardcoded maps) that would touch every existing app's wiring and contradicts ADR-012's
explicit "no framework machinery beyond what the current ~5-screen scale needs" stance. Given the
project is still adding one or two new top-level apps per feature cycle, a checklist enforced at
review time is the proportionate fix; revisit a real registry if a third or fourth app ships with
the same gap despite this ADR.

## Consequences

- **This ADR is the canonical checklist.** Every future `/speckit-plan` for a feature that adds a
  new `application: true` addon MUST reference it (link it from that feature's plan.md) and its
  tasks.md MUST include one task per numbered item above.
- `views/home.js`'s `_renderModuleDetail` fallback (reached only when `_MODULE_HOME_ROUTE` is
  missing) now filters `App.state.models` to the module's own dotted prefix instead of showing
  every model in the system, and shows an explicit "this app may be missing its dedicated home
  screen wiring" empty-state message pointing back at this ADR. A forgotten step 4 now degrades
  to a scoped, self-diagnosing screen instead of a confusing full-system dump — but the other
  steps (menu, breadcrumbs, `modelRouteBase`) still must be done by hand; this fallback is a
  safety net, not a substitute for the checklist.
- `dodoo/addons/product/` and `dodoo/addons/stock_account/` are `application: False` and
  therefore need **none** of the above — this checklist applies only to the one
  `application: true` addon per feature (here, `stock`), not every addon in it.
