from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from dodoo.core.exceptions import AuthenticationError

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)


class SessionManager:
    @staticmethod
    async def authenticate(env: Environment, login: str, password: str) -> str:
        from dodoo.addons.base.models.res_users import ResUsers

        async with env.dml_conn() as conn:
            table = ResUsers._sa_table()
            result = await conn.execute(
                select(table.c.id, table.c.password_hash, table.c.active).where(
                    table.c.login == login
                )
            )
            row = result.fetchone()

        # Same error message for wrong login and wrong password — no user enumeration
        if row is None or not row.active:
            raise AuthenticationError("Authentication failed")

        from argon2 import PasswordHasher
        from argon2.exceptions import VerifyMismatchError

        ph = PasswordHasher()
        try:
            ph.verify(row.password_hash, password)
        except VerifyMismatchError:
            raise AuthenticationError("Authentication failed")

        token = secrets.token_urlsafe(32)  # 256-bit entropy
        expiry_hours = int(os.environ.get("SESSION_EXPIRY_HOURS", "8"))
        expire_date = datetime.now(UTC) + timedelta(hours=expiry_hours)

        async with env.dml_conn() as conn:
            await conn.execute(
                text(
                    "INSERT INTO ir_session (token, user_id, expire_date) "
                    "VALUES (:token, :uid, :expire)"
                ),
                {"token": token, "uid": row.id, "expire": expire_date},
            )
            await conn.commit()

        return token

    @staticmethod
    async def validate(env: Environment, token: str) -> int:
        async with env.dml_conn() as conn:
            result = await conn.execute(
                text("SELECT user_id, expire_date FROM ir_session WHERE token = :token"),
                {"token": token},
            )
            row = result.fetchone()

        if row is None:
            raise AuthenticationError("Invalid or expired session token")

        expire = row.expire_date
        if expire.tzinfo is None:
            expire = expire.replace(tzinfo=UTC)

        if expire < datetime.now(UTC):
            raise AuthenticationError("Invalid or expired session token")

        return int(row.user_id)

    @staticmethod
    async def invalidate(env: Environment, token: str) -> None:
        async with env.dml_conn() as conn:
            await conn.execute(
                text("DELETE FROM ir_session WHERE token = :token"),
                {"token": token},
            )
            await conn.commit()
