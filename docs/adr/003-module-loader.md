# ADR-003: Module Loader — importlib + graphlib.TopologicalSorter

**Status**: Accepted | **Date**: 2026-06-06

## Context
Add-on packages must load in dependency order; circular deps must be detected.

## Decision
Use Python stdlib `importlib.import_module` + `graphlib.TopologicalSorter` (Python 3.9+).

## Consequences
- Zero extra dependencies
- CycleError raised automatically on circular deps
- No dynamic plugin discovery framework overhead
