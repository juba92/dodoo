"""Benchmark fixtures — reuse the hr addon install fixtures (installs base+web+hr).

Feature 006 benchmarks (directory search PERF-001, leave-balance PERF-002) need the hr
schema; the existing tests/benchmarks/test_performance.py builds its own throwaway models
and is unaffected.
"""

from tests.hr.conftest import (  # noqa: F401
    admin_uid,
    company_id,
    db_url,
    env,
    modules_installed,
    pg_container,
)
