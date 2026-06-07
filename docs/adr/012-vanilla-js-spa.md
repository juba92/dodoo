# ADR-012: Vanilla JS ES2022 Modules — No Bundler

**Status**: Accepted
**Date**: 2026-06-07

## Context

The web UI requires JavaScript to implement client-side routing, API communication, and DOM
rendering. The plan prohibits external CDN dependencies and mandates offline capability after
first asset load. This rules out CDN-delivered frameworks (React, Vue, Angular via CDN).
The remaining choice is between a local build toolchain (bundler + framework) or native browser
ES modules with vanilla JS.

## Decision

Use vanilla JavaScript ES2022 with native ES modules (`type="module"`, dynamic `import()`).
No bundler, no transpiler, no framework.

## Rationale

- **No build step**: Every evergreen browser (Chrome 80+, Firefox 78+, Safari 14+) supports
  ES modules natively. Eliminating the build step removes Webpack/Vite/Rollup from the dev
  toolchain — no `node_modules`, no lock files, no build scripts.
- **Offline after first load**: All JS files are served from the addon's `static/` directory
  which is local. Once loaded, navigation works without network access (only API calls fail).
- **Simplicity for scope**: The UI has ~5 screens and ~5 JS modules. A framework adds hundreds
  of lines of boilerplate. Plain JS with a shared `App` object is sufficient and maintainable
  at this scale.
- **Security surface**: No third-party JS packages means no supply-chain risk for the frontend.

## Consequences

- No TypeScript (no compiler). Type safety is achieved through consistent naming and the
  minimal surface area of each module.
- No JSX or template engine — DOM is constructed via `document.createElement` and
  `element.textContent`. All API data is inserted via `textContent` to prevent XSS.
- Each view file exports `{ render(container, params) }`. The router calls `render()` after
  clearing the main container.
- JS unit tests use Node.js built-in `node:test` (no new dependency).

## Alternatives Considered

- **React/Vue with local bundling**: Adds Vite/Webpack, `node_modules`, and a build step.
  Rejected because it contradicts the "no build step" and "offline" requirements.
- **Web Components**: Good encapsulation but verbose — ~200 lines of boilerplate per component
  for a ~5-screen app. Rejected as over-engineering.
- **Single-file app.js with all code**: Hard to maintain past ~500 lines. Rejected in favour
  of one module per view.
