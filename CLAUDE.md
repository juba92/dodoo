<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at `specs/002-web-ui/plan.md`.
<!-- SPECKIT END -->

## Branching Workflow

Each speckit cycle (one feature/module) lives on its own branch named after the spec directory (e.g. `001-erp-core`, `002-web-ui`). Before starting a new cycle, the previous branch must be fully merged into `master` — never branch a new feature from an unmerged feature branch. Once merged, create the new branch from `master`. Branches are kept after merging (do not delete them). This means `master` always represents the last fully completed module, and each feature branch is a clean diff on top of it.
