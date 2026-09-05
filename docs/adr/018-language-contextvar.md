# ADR-018: Request-scoped language + uid via contextvars

**Status**: Accepted | **Date**: 2026-09-05

## Context

`dodoo.Environment` is a process singleton created once at startup, not per-request. Server-side
translation of model field labels needs the effective UI language, and `res.config.settings`
methods invoked over JSON-RPC need the caller `uid` — but `_object_execute_kw` injects `uid` only
for `search`/`search_read`. Threading `lang`/`uid` through every ORM entry point would touch the
whole codebase.

## Decision

Add `dodoo/core/context.py` with `lang_var: ContextVar[str]` (default `"en"`) and
`uid_var: ContextVar[int | None]` (default `None`), plus `get_/set_` helpers. A `LanguageMiddleware`
(registered after `CorrelationMiddleware`) validates the session token once per request, sets
`uid_var`, resolves the effective language (`res_users.lang` → `res_company.lang` → `"ar"`), and
sets `lang_var`. `BaseModel.fields_get` runs each label through `translate(label, get_lang())`;
`res.config.settings` reads `get_uid()`.

## Consequences

- Asyncio-safe; no ORM signature changes; mirrors Odoo's `context['lang']` propagation.
- The `fields_get` hook is inert without the `localization` addon (empty catalog → identity), and
  `uid_var` is simply `None` outside an authenticated request.
- The company default language is cached in a module variable, invalidated on a `res_company` write,
  so per-request resolution is one dict lookup plus (only with a token) one indexed `res_users` read.
- Rejected: per-request `Environment` clone (large refactor); injecting `uid` into every dispatcher
  method (spreads plumbing, still leaves menu/system strings unsolved).
