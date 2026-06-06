"""Performance benchmarks — PERF-001, PERF-002, PERF-003.

Run with: pytest tests/benchmarks/ -v --timeout=120
These tests require a live PostgreSQL instance (uses the env fixture).
"""

from __future__ import annotations

import asyncio
import time

import pytest

from dodoo.core.fields import Char, Integer
from dodoo.core.migration import MigrationRunner
from dodoo.core.models import BaseModel


class BenchModel(BaseModel):
    _name = "bench.model"
    title = Char(size=256)
    score = Integer()


@pytest.fixture(scope="module", autouse=True)
async def setup_bench_table(env):
    runner = MigrationRunner(env._ddl_engine)
    try:
        env.registry.register(BenchModel)
    except Exception:
        pass
    await runner.install(BenchModel)

    # Seed 100k rows
    from sqlalchemy import text

    async with env._ddl_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO bench_model (title, score) "
                "SELECT 'Record ' || g, g FROM generate_series(1, 100000) g "
                "ON CONFLICT DO NOTHING"
            )
        )


async def test_perf_001_single_record_lookup_p95(env):
    """PERF-001: p95 single-record lookup by ID < 10ms on 100k-row table."""
    ids = await BenchModel.search(env, [], limit=100)
    assert ids, "Need seeded records for benchmark"

    times = []
    for rec_id in ids[:50]:
        start = time.perf_counter()
        records = await BenchModel.read(env, [rec_id])
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert len(records) == 1
        times.append(elapsed_ms)

    times.sort()
    p95 = times[int(len(times) * 0.95)]
    assert p95 < 10.0, f"PERF-001 violated: p95={p95:.2f}ms (limit 10ms)"


async def test_perf_002_jsonrpc_throughput(env):
    """PERF-002: JSON-RPC throughput >= 200 req/s on localhost."""
    from httpx import ASGITransport, AsyncClient

    from dodoo.http.app import create_app
    from dodoo.http.routing import RouteRegistry

    RouteRegistry.reset()
    import dodoo.addons.base.http  # noqa: F401

    app = create_app(env)
    transport = ASGITransport(app=app)

    n_requests = 100
    start = time.perf_counter()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tasks = [
            client.post(
                "/jsonrpc",
                json={
                    "jsonrpc": "2.0",
                    "method": "call",
                    "id": i,
                    "params": {"service": "common", "method": "version", "args": [], "kwargs": {}},
                },
            )
            for i in range(n_requests)
        ]
        responses = await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - start
    throughput = n_requests / elapsed
    assert throughput >= 200, f"PERF-002 violated: {throughput:.1f} req/s (limit 200)"
    for r in responses:
        assert r.status_code == 200


async def test_perf_003_module_install_time(env):
    """PERF-003: 10 synthetic modules × 5 models installs in < 5s."""
    import os
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Create 10 synthetic add-ons
        for i in range(10):
            pkg = tmp_path / f"synth_mod_{i}"
            pkg.mkdir()
            (pkg / "__manifest__.py").write_text(
                repr({"name": f"synth_mod_{i}", "version": "1.0.0", "depends": []})
            )
            models_code = "\n".join(
                f"""
from dodoo.core.fields import Char
from dodoo.core.models import BaseModel

class SynthModel{i}_{j}(BaseModel):
    _name = "synth.{i}.{j}"
    label = Char(size=128)
"""
                for j in range(5)
            )
            (pkg / "__init__.py").write_text(models_code)

        os.environ["ADDONS_PATH"] = tmp

        from dodoo.modules.installer import ModuleInstaller

        installer = ModuleInstaller(env)

        start = time.perf_counter()
        for i in range(10):
            await installer.install(f"synth_mod_{i}")
        elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"PERF-003 violated: {elapsed:.2f}s (limit 5s)"
