"""Structured transition logging for HR / Fleet workflows (FR-066, FR-067a, Principle IX).

``dodoo.core.logging._JsonFormatter`` only serialises a fixed field set plus the rendered
message, so the audit payload is encoded into the message text as ``key=value`` tokens (which
always survive) *and* passed as ``extra=`` for any future formatter that emits it. The
``correlation_id`` is attached by ``CorrelationMiddleware``.

Never pass PII (names, feedback text, wages, bank / ID numbers) — identifiers and states only
(SEC-006).
"""

from __future__ import annotations

import logging
from typing import Any


def log_transition(
    logger: logging.Logger,
    *,
    model: str,
    record_id: int,
    event: str,
    frm: str | None = None,
    to: str | None = None,
    actor_uid: int | None = None,
    company_id: int | None = None,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit one structured transition/approval log entry."""
    payload: dict[str, Any] = {
        "model": model,
        "record_id": record_id,
        "event": event,
        "actor_uid": actor_uid,
    }
    if frm is not None:
        payload["from"] = frm
    if to is not None:
        payload["to"] = to
    if company_id is not None:
        payload["company_id"] = company_id
    payload.update(fields)

    tokens = " ".join(f"{k}={v}" for k, v in payload.items() if v is not None)
    logger.log(level, "hr.transition %s", tokens, extra=payload)


def log_conflict(
    logger: logging.Logger,
    *,
    model: str,
    record_id: int,
    event: str,
    expected: str | None,
    actual: str | None,
    actor_uid: int | None = None,
) -> None:
    """Emit a from-state precondition rejection (FR-067a) at WARNING."""
    log_transition(
        logger,
        model=model,
        record_id=record_id,
        event=event,
        frm=actual,
        to=expected,
        actor_uid=actor_uid,
        level=logging.WARNING,
        conflict="1",
    )
