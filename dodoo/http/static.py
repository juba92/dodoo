"""Static-file serving helpers.

``NoCacheStaticFiles`` serves the SPA's assets with ``Cache-Control: no-cache`` so a
browser always revalidates (a cheap ETag round-trip → ``304`` when unchanged) instead
of running a stale bundle from its heuristic cache after an addon is updated. The
byte payload is still only re-sent when the file actually changes.
"""

from __future__ import annotations

import os
from typing import Any

from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class NoCacheStaticFiles(StaticFiles):
    def __init__(self, *, directory: str, **kwargs: Any) -> None:
        # Git doesn't track empty directories, so an addon whose static/ tree has
        # no files yet (e.g. backend-only so far, no SPA views) simply isn't
        # present after a fresh clone/deploy — Starlette's StaticFiles refuses to
        # mount a missing directory, which crashed the whole module install
        # (product/http/__init__.py mounts /product/static before it has any
        # content). Creating it is harmless and keeps addon http/__init__.py
        # modules from each needing their own mkdir boilerplate.
        os.makedirs(directory, exist_ok=True)
        super().__init__(directory=directory, **kwargs)

    def file_response(
        self,
        full_path: Any,
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Any:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "no-cache"
        return response
