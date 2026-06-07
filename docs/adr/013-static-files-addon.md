# ADR-013: Serving Static Files via a FastAPI Addon

**Status**: Accepted
**Date**: 2026-06-07

## Context

The web UI needs its HTML, CSS, and JS files served over HTTP from the same origin as the API
server. Options include: a separate static server (Nginx, Caddy), serving files through custom
FastAPI route handlers, or using Starlette's built-in `StaticFiles` ASGI application mounted
on the FastAPI app.

## Decision

Mount `starlette.staticfiles.StaticFiles` at `/web/static/` in the `web` addon's
`http/__init__.py`, using a `MountRegistry` that `create_app()` applies after route
registration. Register a separate `GET /web/client` route that returns the `index.html` file.

## Rationale

- **Zero new runtime dependencies**: `StaticFiles` is part of Starlette, which is already a
  FastAPI dependency. No additional packages are introduced.
- **Correct caching headers**: `StaticFiles` automatically emits `Last-Modified`, `ETag`,
  `Cache-Control`, and `Content-Type` headers — far better than hand-rolling a file-serving
  route handler.
- **Self-contained addon**: The `web` addon registers both its REST route and its static mount
  from within `http/__init__.py`. No changes to core routing are needed beyond adding
  `MountRegistry` (a ~20-line addition to `routing.py`).
- **Separation of concerns**: `/web/client` (returns `index.html`) and `/web/static/*` (serves
  JS/CSS) are cleanly separated — the entry point can be controlled independently of assets.

## Consequences

- `MountRegistry` is added to `dodoo/http/routing.py` and called from `create_app()` after
  `RouteRegistry.register_with_app()`. Routes are matched before mounts (Starlette's default
  ordering is preserved).
- The static directory path is resolved relative to `__file__` at import time, so the files
  are always found regardless of the working directory when the server is started.

## Alternatives Considered

- **Nginx / separate static server**: Correct for production but out of scope for single-process
  localhost deployment. Rejected.
- **Custom `FileResponse` route handlers per file**: Verbose, misses caching headers, and
  doesn't scale to a directory of assets. Rejected.
- **Serve from the core `dodoo/http/` package**: Breaks addon isolation — core would need
  to know about the web addon's files. Rejected.
