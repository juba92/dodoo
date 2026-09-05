"""Request-scoped context.

``Environment`` is a process singleton, so per-request values (the effective UI language,
the authenticated user id) travel in :class:`contextvars.ContextVar` set once per request by
``LanguageMiddleware``. ``BaseModel.fields_get`` reads :func:`get_lang`; the settings model
methods read :func:`get_uid` because the JSON-RPC dispatcher injects ``uid`` only for
``search`` / ``search_read``.
"""

from __future__ import annotations

from contextvars import ContextVar

lang_var: ContextVar[str] = ContextVar("dodoo_lang", default="en")
uid_var: ContextVar[int | None] = ContextVar("dodoo_uid", default=None)


def get_lang() -> str:
    return lang_var.get()


def set_lang(code: str) -> None:
    lang_var.set(code or "en")


def get_uid() -> int | None:
    return uid_var.get()


def set_uid(uid: int | None) -> None:
    uid_var.set(uid)
