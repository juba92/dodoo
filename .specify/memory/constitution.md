<!--
## Sync Impact Report

**Version Change**: N/A → 1.0.0 (initial ratification)

**Principles Added**:
- I. Code Quality & Consistency (new)
- II. Comprehensive Testing Standards (new)
- III. Security-First Design (new)
- IV. Performance Requirements (new)
- V. Documentation Standards (new)
- VI. Accessibility & UX Consistency (new)
- VII. Dependency Hygiene (new)
- VIII. CI/CD Gate Requirements (new)
- IX. Observability (new)

**Sections Added**:
- Core Principles (9 principles)
- Quality Gates
- Governance

**Templates Updated**:
- ✅ `.specify/templates/plan-template.md` — Constitution Check gates aligned with 9 principles
- ✅ `.specify/templates/spec-template.md` — Requirements extended with security, performance, accessibility
- ✅ `.specify/templates/tasks-template.md` — Foundational and Polish phases reflect principle-driven task types

**Deferred Items**: None
-->

# Dodoo Constitution

## Core Principles

### I. Code Quality & Consistency

All code MUST pass linting and formatting checks before merge. Naming conventions MUST follow
the project's established style guide or language idioms. Formatters and linters MUST be enforced
in CI — local-only compliance is insufficient.

**Non-negotiable rules**:
- Zero linting errors on merge; warnings are treated as errors in CI
- Formatter (e.g., Prettier, Black, gofmt) applied automatically — no manual formatting exceptions
- Naming: descriptive, unabbreviated, consistent casing per language convention
- Dead code MUST be removed; commented-out code is prohibited without an ADR link

**Rationale**: Consistency eliminates cognitive overhead and prevents stylistic drift that
compounds into maintenance debt over time.

### II. Comprehensive Testing Standards

All features MUST have test coverage across unit, integration, and end-to-end (e2e) layers.
Coverage thresholds MUST be enforced in CI (minimum 80% line coverage for unit tests; 100% branch
coverage for critical paths). Mocking external system boundaries (databases, third-party APIs,
message brokers) is permitted ONLY with written justification — silent mocks are prohibited.

**Non-negotiable rules**:
- Unit tests: MUST cover all business logic; coverage threshold enforced by CI
- Integration tests: MUST cover all inter-service communication and data persistence paths
- E2e tests: MUST cover all primary user journeys defined in the feature spec
- Test-first (TDD) RECOMMENDED for new logic; tests MUST exist before merge regardless
- External boundary mocks MUST be justified in the PR or test file; prefer test containers or
  contract tests

**Rationale**: Silent mocks mask integration failures. Coverage thresholds prevent regression
blind spots. Layered testing provides confidence at the right granularity.

### III. Security-First Design

All features MUST comply with OWASP Top 10. Input validation MUST occur at every system boundary
(API endpoints, CLI arguments, file ingestion, message queues). The principle of least privilege
MUST govern all service accounts, IAM roles, database users, and API keys.

**Non-negotiable rules**:
- Input validation: whitelist-based, enforced at the boundary, before any downstream processing
- Authentication and authorization MUST be enforced on every protected resource
- Secrets MUST NOT appear in source code, logs, or error messages
- OWASP Top 10 checklist MUST be reviewed for every feature touching auth, data, or external I/O
- Threat model MUST be documented in the ADR for any architectural change (see Principle V)
- Dependencies MUST be audited for CVEs before introduction (see Principle VII)

**Rationale**: Security failures are often irreversible. Boundary validation and least-privilege
stop the majority of attack vectors before they escalate.

### IV. Performance Requirements

Every feature MUST define measurable latency and throughput targets before implementation begins.
Targets MUST be captured in plan.md. No known performance regressions are permitted — CI MUST
include baseline benchmarks for critical paths. Premature optimization is prohibited; all
optimization work MUST be justified by measured profiling data.

**Non-negotiable rules**:
- Performance targets MUST be stated in plan.md before implementation (e.g., p95 < 200ms, ≥ 1000 req/s)
- Benchmark tests MUST exist for critical paths and run in CI
- Regressions exceeding 10% degradation from baseline block merge
- Optimization work MUST reference profiling data — no speculative optimization
- Memory and resource bounds MUST be specified for memory-sensitive environments

**Rationale**: Unmeasured performance is unmanaged performance. Explicit targets prevent
scope creep disguised as optimization and create accountability.

### V. Documentation Standards

Architectural decisions MUST be recorded as Architecture Decision Records (ADRs) in `docs/adr/`.
Inline code comments MUST explain WHY, not WHAT. Redundant comments restating obvious logic MUST
be removed. Public APIs MUST have concise interface-level documentation.

**Non-negotiable rules**:
- Every architectural decision (technology choice, pattern selection, schema design) REQUIRES an ADR
- ADR format: title, status, context, decision, consequences
- Inline comments: zero tolerance for "what" comments; "why" comments permitted only for
  non-obvious rationale, hidden constraints, or known workarounds
- Public API docs: one-line summary + parameter contracts; no multi-paragraph docstrings
- Planning or analysis documents MUST NOT be embedded in source files

**Rationale**: Code explains mechanism; ADRs explain intent. Without WHY documentation,
future contributors repeat past mistakes or undo deliberate constraints.

### VI. Accessibility & UX Consistency

All user-facing interfaces MUST meet WCAG 2.1 AA accessibility standards. UX patterns (navigation,
error states, loading states, form interactions) MUST be consistent across the application.
Accessibility MUST be validated before feature sign-off — retrofitting is not acceptable.

**Non-negotiable rules**:
- Color contrast MUST meet WCAG 2.1 AA (≥ 4.5:1 for normal text, ≥ 3:1 for large text)
- All interactive elements MUST be keyboard-navigable
- Screen reader compatibility MUST be tested (ARIA labels, semantic HTML/components)
- Error messages MUST be descriptive, actionable, and not conveyed by color alone
- UX patterns MUST follow the project's design system — no ad-hoc divergence without ADR

**Rationale**: Inaccessible interfaces exclude users and create legal exposure. UX consistency
reduces cognitive load and support burden.

### VII. Dependency Hygiene

No unused dependencies are permitted. All dependency versions MUST be pinned with lock files
committed. Every new dependency MUST pass a CVE audit before introduction. Dependencies MUST be
reviewed for license compatibility.

**Non-negotiable rules**:
- Lock files (package-lock.json, poetry.lock, go.sum, etc.) MUST be committed and kept current
- CVE audit tools (npm audit, pip-audit, govulncheck, or equivalent) MUST run in CI and block
  on HIGH or CRITICAL severity findings
- Unused dependencies MUST be removed before merge
- Dependency additions MUST be justified in the PR — no transitive bloat without review
- License compatibility MUST be verified for every new OSS dependency

**Rationale**: Unused and unaudited dependencies are attack surface. Pinned versions ensure
reproducible builds and prevent supply-chain surprises.

### VIII. CI/CD Gate Requirements

All CI checks MUST pass before any branch is merged. Bypassing CI (--no-verify, force-merge,
skip-checks) is strictly prohibited. CI gates MUST enforce: linting, formatting, tests (all layers),
security scans, dependency audits, build success, and coverage thresholds.

**Non-negotiable rules**:
- MUST NOT merge with failing CI — no exceptions without post-incident documentation
- `--no-verify` and equivalent bypass flags are prohibited across all environments
- Branch protection MUST require CI pass and at least one peer review before merge
- Hotfixes follow the same gate process — urgency is not a justification for bypass
- CI pipeline definition MUST be version-controlled; changes require peer review

**Rationale**: CI is the last line of defense before production. Bypass culture erodes trust
in the pipeline and reintroduces exactly the failure classes CI was designed to catch.

### IX. Observability

All services MUST emit structured logs (JSON or equivalent) at appropriate verbosity levels.
Error tracing MUST include correlation IDs that span service boundaries. Alerting hooks MUST be
configured for all critical paths. Silent failures are prohibited.

**Non-negotiable rules**:
- Structured logging: every log entry MUST include timestamp, level, service, correlation_id, message
- Log levels: ERROR (actionable, requires response), WARN (degraded state), INFO (lifecycle events),
  DEBUG (disabled in production)
- Distributed traces MUST propagate context headers across service calls
- Alerts MUST be configured for: error rate spikes, latency threshold breaches, critical job failures
- Health check endpoints MUST exist for all services and be monitored
- No swallowed exceptions — all errors MUST be logged or surfaced to the caller

**Rationale**: Unobservable systems cannot be reliably operated. Structured logs enable machine
parsing; correlation IDs make distributed failures diagnosable; alerting ensures humans are
notified before users are.

## Quality Gates

The following gates MUST pass at each development milestone:

| Gate | When | Owner |
|------|------|-------|
| Linting + formatting clean | Every commit (pre-commit + CI) | Developer |
| Unit test coverage ≥ 80% | Every PR | CI |
| Integration tests pass | Every PR | CI |
| E2e tests pass | Every PR to main | CI |
| Security scan (OWASP / CVE audit) | Every PR | CI |
| Performance benchmark ≤ baseline + 10% | Every PR touching critical paths | CI |
| ADR filed for architectural decisions | Before implementation begins | Lead |
| Accessibility audit (WCAG 2.1 AA) | Before feature sign-off | Developer + QA |
| Dependency audit (no HIGH/CRITICAL CVEs) | Every PR with dependency changes | CI |
| All CI checks green | Before merge | CI + Reviewer |

## Governance

This constitution supersedes all prior practices, README instructions, and informal agreements.
Amendments require:

1. A written proposal in ADR format explaining the change and rationale
2. Peer review by at least two contributors
3. Version bump per semantic versioning rules:
   - MAJOR: principle removals, backward-incompatible governance changes
   - MINOR: new principle added or materially expanded guidance
   - PATCH: clarifications, wording fixes, non-semantic refinements
4. Updated `LAST_AMENDED_DATE` committed to main

All PRs and code reviews MUST verify compliance with applicable principles. Constitution violations
discovered in review MUST block merge — no "fix it later" deferrals.

Compliance reviews MUST occur at each feature retrospective. Persistent violations require a
root-cause analysis and process amendment, not individual blame.

**Version**: 1.0.0 | **Ratified**: 2026-06-06 | **Last Amended**: 2026-06-06
