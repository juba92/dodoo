<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at `specs/003-accounting/plan.md`.
<!-- SPECKIT END -->

## Odoo Reference Implementation

The goal of this project is to produce an Odoo-like product. The Odoo source code is cloned at `../odoo-19.0` and **must be studied before designing any feature** — UI layout, ORM patterns, module structure, HTTP routing, field types, access rules, and view architecture should all be modelled after how Odoo implements them. When in doubt about how something should work, read the equivalent in `../odoo-19.0` first.

## Branching Workflow

Each speckit cycle (one feature/module) lives on its own branch named after the spec directory (e.g. `001-erp-core`, `002-web-ui`). Before starting a new cycle, the previous branch must be fully merged into `master` — never branch a new feature from an unmerged feature branch. Once merged, create the new branch from `master`. Branches are kept after merging (do not delete them). This means `master` always represents the last fully completed module, and each feature branch is a clean diff on top of it.

## Speckit Automation Rules

These rules govern the automated speckit workflow and MUST be followed exactly:

### Clarification (speckit-clarify)
When `/speckit-clarify` runs — whether invoked manually or automatically after `/speckit-specify` — **all clarification questions MUST be answered autonomously**. Do not ask the user. Choose the option that best satisfies all of the following criteria in priority order:
1. Matches the project constitution's principles and governance constraints
2. Matches dodoo's existing architecture and design patterns (FastAPI, SQLAlchemy Core async, Pydantic v2, vanilla JS SPA)
3. Matches how Odoo 19.0 implements the equivalent feature (read `../odoo-19.0` source when needed)
4. Minimises implementation scope while preserving correctness and forward-compatibility

After choosing, state the selected option and the one-sentence rationale, then proceed immediately. Never wait for user confirmation on clarification questions.

### Analysis & Remediation (speckit-analyze)
When `/speckit-analyze` runs — whether invoked manually or automatically after `/speckit-tasks` — **all findings MUST be resolved before reporting completion**, regardless of severity level (CRITICAL, HIGH, MEDIUM, LOW). Resolution means editing the relevant artifact files (spec.md, plan.md, tasks.md) to eliminate the finding. After all findings are resolved, commit the changes via the after_analyze hook and report the final clean state to the user.
