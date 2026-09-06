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
