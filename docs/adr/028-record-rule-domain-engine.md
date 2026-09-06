# ADR-028: Record-rule domain engine — user context + relational leaves

**Status**: Accepted | **Date**: 2026-09-06 | **Feature**: 006-human-resources

## Context

`dodoo.core.query.compile_domain` only understood flat, literal, single-column leaves.
`AccessEnforcer` stored `ir.rule.domain_filter` as static JSON and `models.search` compiled it
with no notion of the current user. So an `ir.rule` could not express "rows owned by the calling
user" or "rows in the user's company", and could not traverse a relation
(`employee_id.user_id = <me>`). The HR security model (FR-059…FR-064, SC-006, SC-007) is built
entirely on such rules, and the existing engine also had a latent failure-open bug:
`_get_access_domain` swallowed every exception and returned `None`, which `search` treats as
"no restriction".

## Decision

**`compile_domain(table, fields, domain, *, context=None, resolve=None)`** — two new keyword-only,
backward-compatible parameters:

- **`context`**: a dict `{"uid", "company_id", "company_ids"}`. A leaf value that is a string
  beginning with `$` is a placeholder resolved from the context: `$uid`, `$company_id`,
  `$company_ids`, `$today`. Placeholders inside a list value (for `in` / `not in`) are resolved
  element-wise. An unknown `$token` raises `DomainError`. Domain filters are addon-seeded, never
  user-supplied, so a literal value that happens to start with `$` is out of scope.
- **`resolve`**: a callable `(model_name) -> (sa.Table, {name: Field})`. When a leaf field name
  contains a dot, `head.rest` is compiled as a correlated subquery:
  `table.c[head].in_(select(rel.c.id).where(<rest compiled against rel>))`, recursing for
  multi-hop paths. `head` must be a `Many2one` (carry a `.relation`).
- `= None` / `!= None` now compile to `IS NULL` / `IS NOT NULL`.

**`AccessEnforcer.build_context(env, uid)`** returns the context dict. `company_ids` is every
`res.company` id (one today; a `res.users.company_ids` M2M replaces this when multi-company lands).

**`models.search`** builds the context and a registry-backed `resolve` closure and passes both when
compiling the rule clause. If rule compilation raises `DomainError` (a malformed rule), `search`
logs at ERROR and applies `sa.false()` — **fail closed**, never open. `_get_access_domain` no
longer silently swallows errors; a genuine infrastructure error still degrades to "no extra
restriction" but is logged.

## Scope boundary

Rule enforcement stays on the `search` / `search_read` path (every SPA list / Kanban / calendar
view and every `execute_kw` list call goes through it). A direct `read([id])` with a known id is
**not** rule-filtered — `read` has no `uid` parameter and threading one through `_ModelProxy` and
the JSON-RPC dispatcher is a separate change. Models holding sensitive columns (e.g.
`hr.employee`) drop those columns in their own `read` override for non-owner / non-officer callers
(the `res.users.read` / `password_hash` precedent). `write` / `unlink` rule enforcement is also
out of scope here; mutations are gated by the REST action group checks (FR-067) and model-layer
guards.

## Consequences

- `ir.rule` becomes the real enforcement mechanism for read access, Odoo-faithfully, including
  ownership (`user_id = $uid`), company scope (`company_id in $company_ids`), and one/two-hop
  relational rules (`employee_id.manager_id.user_id = $uid`).
- One `EXISTS`/`IN (subquery)` per relational hop — acceptable at the row counts in PERF-001…004;
  rules are kept to ≤ 2 hops.
- Fail-closed on a broken rule is a deliberate security choice (Principle III least privilege,
  Principle IX no silent failures).
- Rejected: model-layer enforcement per addon (005 precedent) — keeps `core` untouched but
  scatters the policy across every model's overrides and diverges from the `ir.rule` design in
  plan.md / data-model.md. Rejected: a `$uid`-only flat-domain shim with denormalised
  `*_user_id` columns — smaller, but forces a denormalised column per ownership relation and still
  can't do manager-chain rules.
