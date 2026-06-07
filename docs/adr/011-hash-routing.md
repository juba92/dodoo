# ADR-011: Hash-Based Routing for the Web SPA

**Status**: Accepted
**Date**: 2026-06-07

## Context

The dodoo web UI is a single-page application served as static files from FastAPI. Client-side
navigation must update the URL so that links are bookmarkable and the browser Back button works,
without triggering a full page reload. Two standard approaches exist: History API (`pushState`)
and hash-based routing (`window.location.hash`).

## Decision

Use hash-based routing (`#/login`, `#/home`, `#/model/res.users`, etc.).

## Rationale

- **No server configuration required**: The fragment (`#...`) is never sent to the server. Every
  URL with any hash still resolves to the same `/web/client` endpoint, returning `index.html`.
  History API routing requires a server-side catch-all that maps arbitrary paths back to
  `index.html` — this would mean touching FastAPI routing for every possible UI path.
- **Self-contained addon**: The web addon mounts one route (`/web/client`) and one static
  directory (`/web/static/`). Hash routing keeps it fully self-contained; no changes to core
  routing are needed.
- **Bookmarkability and Back button**: Hash changes fire `hashchange` events which the router
  intercepts to update the view. The browser preserves hash history, so Back/Forward work
  correctly.

## Consequences

- URLs contain `#` fragments (e.g., `http://localhost:8069/web/client#/model/res.users`).
- Screen readers and crawlers do not follow hash routes, but this is acceptable for a
  single-tenant localhost ERP tool where SEO is irrelevant.
- All navigation in JS must use `window.location.hash = ...` or `App.navigate(hash)`.

## Alternatives Considered

- **History API (`pushState`)**: Cleaner URLs but requires a server-side catch-all route.
  Rejected because it breaks addon isolation — the server would need path-level changes for
  every UI route.
- **Single giant HTML with hidden sections**: No bookmarkability or URL persistence. Rejected
  as it violates usability requirements.
