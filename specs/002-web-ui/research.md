# Research: Dodoo Web UI

## 1. SPA Routing Without a Framework

**Decision**: Hash-based routing (`#/login`, `#/home`, `#/model/res.users`, `#/model/res.users/1`)

**Rationale**: Hash routing requires zero server configuration — the server always returns `index.html` and the fragment is handled entirely in the browser. History API (`pushState`) routing requires the server to handle arbitrary paths, which would mean touching FastAPI routes for every possible UI path. Hash routing keeps the addon fully self-contained.

**Alternatives considered**:
- History API routing: cleaner URLs but requires server-side catch-all route
- Single giant HTML file with hidden sections: no bookmarkability, poor separation

---

## 2. State Management

**Decision**: A single global `App` object with explicit `render()` calls. State held in memory; session token in `sessionStorage`.

**Rationale**: Frameworks (React, Vue, Svelte) are excluded by spec. The MVC alternative (Backbone-style) adds boilerplate. A plain JS module with a `state` object and `navigate(route)` function is the simplest correct pattern for this scope.

**Alternatives considered**:
- Web Components: good isolation but verbose and adds ~200 lines of boilerplate per component
- Template literals + diffing: over-engineering for a ~5-screen app

---

## 3. Serving Static Files from the Addon

**Decision**: Mount `StaticFiles` at `/web/static/` via FastAPI in the addon's `http/__init__.py`. Register a catch-all GET route at `/web/client` that returns `index.html`.

**Rationale**: FastAPI's `StaticFiles` from Starlette is already a dependency (via FastAPI). No new dependency needed. The addon simply mounts its `static/` directory.

**Alternatives considered**:
- Serve files via custom route handlers: verbose, misses caching headers
- Nginx/separate static server: out of scope for single-process local deployment

---

## 4. API Communication Layer

**Decision**: A thin `api.js` module that wraps `fetch()`. Provides `rpc(service, method, args, kwargs)` and `call(endpoint, body)` helpers. Reads token from `sessionStorage` and injects it as `X-Session-Token` header.

**Rationale**: Centralising all fetch calls in one module makes it easy to inject the token, handle 401 redirects, and mock in tests.

**Alternatives considered**:
- Inline fetch() calls per view: duplicates token injection and error handling

---

## 5. End-to-End Testing

**Decision**: Playwright (Python, `playwright` package) for e2e tests. Tests live in `tests/e2e/test_web_ui.py`.

**Rationale**: Playwright supports headless Chromium, has excellent async support matching the rest of the test suite, and works in CI without a display server. It's the most capable browser automation tool available in Python.

**Alternatives considered**:
- Selenium: older API, heavier setup
- Cypress: JavaScript-only, incompatible with Python test suite
- Manual testing: not acceptable per constitution

---

## 6. Accessibility Implementation

**Decision**: Semantic HTML (`<nav>`, `<main>`, `<table>`, `<form>`, `<button>`), ARIA live regions for status messages, visible focus rings via CSS `:focus-visible`.

**Rationale**: Semantic HTML gives screen readers correct context for free. ARIA live regions are the standard mechanism for announcing dynamic content changes.

**Alternatives considered**:
- `role="application"` on body: reduces AT context, not recommended for document-like UIs

---

## 7. No-Build Vanilla JS Module Strategy

**Decision**: Each view is a plain JS file that exports a `render(container)` function. `app.js` loads them with dynamic `import()`. No bundler, no transpilation.

**Rationale**: Modern browsers support ES modules natively. `import()` is supported in all evergreen browsers. This eliminates all build tooling while keeping files modular.

**Alternatives considered**:
- Single-file `app.js` with everything: hard to maintain past ~500 lines
- Webpack/Vite: adds a build step and dev server dependency, contradicts offline-first requirement
