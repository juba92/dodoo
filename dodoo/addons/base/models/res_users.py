from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from dodoo.core.fields import Boolean, Char, Many2many
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

_ph = PasswordHasher()


class ResUsers(BaseModel):
    _name = "res.users"

    login = Char(size=128, required=True)
    password_hash = Char(size=256, readonly=True)
    name = Char(size=256, required=True)
    active = Boolean(default=True)
    # Personal language preference (005). NULL/empty ⇒ fall back to res.company.lang
    # when resolving the effective language for a request.
    lang = Char(size=16)
    group_ids = Many2many(
        "res.groups",
        relation_table="res_users_groups_rel",
        column1="user_id",
        column2="group_id",
    )

    @classmethod
    async def read(
        cls, env: Environment, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        # Never expose password_hash in read results
        if fields is None:
            fields = [f for f in cls._all_field_names() if f != "password_hash"]
        else:
            fields = [f for f in fields if f != "password_hash"]
        return await super().read(env, ids, fields)

    @classmethod
    def _check_password(cls, plain: str, hashed: str) -> bool:
        try:
            _ph.verify(hashed, plain)
            return True
        except VerifyMismatchError:
            return False

    @classmethod
    def _hash_password(cls, plain: str) -> str:
        return _ph.hash(plain)
