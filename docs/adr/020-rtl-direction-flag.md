# ADR-020: RTL via a direction flag + [dir=rtl] CSS overrides

**Status**: Accepted | **Date**: 2026-09-05

## Context

Arabic requires a right-to-left web UI. The SPA has no build step or CSS tooling.

## Decision

The `/web/i18n/{lang}.json` payload carries `direction`. `i18n.js#applyDirection` sets
`<html dir lang>`. `style.css` gains a small `[dir="rtl"]` block that mirrors the shell chrome
(header brand border/margin, sidebar side + active-item accent, breadcrumb separator, user-area
alignment). No second stylesheet, no PostCSS.

## Consequences

- One stylesheet, no bundler; matches the project's no-tooling front end.
- New chrome CSS should prefer logical properties so the override block stays small.
- Rejected: a separate `style.rtl.css` (drift risk); an `rtlcss` build step (new tooling).
