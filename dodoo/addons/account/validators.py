"""Whitelist validation at the HTTP/RPC boundary (SEC-001) and group checks (SEC-002/003).

``account``'s first validators file (research.md D8) — every REST action body added by this
feature is parsed through a Pydantic v2 model with ``extra="forbid"``.
"""

from __future__ import annotations

import datetime as _dt
import re
from decimal import Decimal
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import text

from dodoo.core.exceptions import AccessError, DodooError

_M = TypeVar("_M", bound=BaseModel)


class Payload(BaseModel):
    """Base for every action payload model — forbids unknown fields."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())


def validate(model_cls: type[_M], payload: dict[str, Any] | None) -> _M:
    """Parse ``payload`` into ``model_cls`` or raise ``DodooError`` with a stable code."""
    try:
        return model_cls.model_validate(payload or {})
    except ValidationError as exc:
        errs = exc.errors()
        if any(e.get("type") == "extra_forbidden" for e in errs):
            bad = ", ".join(
                str(e["loc"][-1]) for e in errs if e.get("type") == "extra_forbidden"
            )
            raise DodooError(f"unknown_field: {bad}") from exc
        loc = errs[0].get("loc") or ("",)
        raise DodooError(f"invalid_payload: {loc[-1]} {errs[0]['msg']}") from exc


async def group_names(env: Any, uid: int | None) -> set[str]:
    """Return the set of ``res.groups`` names the user belongs to."""
    if not uid:
        return set()
    async with env.dml_conn() as conn:
        rows = await conn.execute(
            text(
                "SELECT g.name FROM res_users_groups_rel r "
                "JOIN res_groups g ON g.id = r.group_id WHERE r.user_id = :uid"
            ),
            {"uid": uid},
        )
        return {row[0] for row in rows}


async def is_member(env: Any, uid: int | None, name: str) -> bool:
    return name in await group_names(env, uid)


async def require_groups(env: Any, uid: int | None, *names: str) -> None:
    """Raise ``AccessError`` unless the user is in at least one of ``names``.

    The ``Administrator`` superuser group always passes.
    """
    held = await group_names(env, uid)
    if "Administrator" in held:
        return
    if held.isdisjoint(names):
        raise AccessError(f"requires one of: {', '.join(names)}")


# --------------------------------------------------------------------------- US3 (coa/journals/audit-trail)


class ReverseMove(Payload):
    date: _dt.date | None = None
    journal_id: int | None = None
    auto_post: bool = True


class HashChainToggle(Payload):
    enabled: bool


class CancelMove(Payload):
    pass  # empty body; kept as a named model for consistency with every other action route


class LockExceptionGrant(Payload):
    company_id: int
    lock_date_field: Literal[
        "fiscalyear_lock_date", "tax_lock_date", "sale_lock_date", "purchase_lock_date"
    ]
    lock_date: _dt.date
    user_id: int | None = None
    journal_id: int | None = None
    end_date: _dt.date


# --------------------------------------------------------------------------- US1 (invoicing/tax/payment-terms)


class AccountTagCreate(Payload):
    name: str = Field(min_length=1, max_length=128)
    applicability: Literal["taxes"] = "taxes"
    country_id: int | None = None


class PaymentTermLineCreate(Payload):
    payment_term_id: int
    sequence: int = 10
    value: Literal["percent", "fixed"]
    value_amount: Decimal
    delay_type: Literal[
        "days_after",
        "days_after_end_of_month",
        "days_after_end_of_next_month",
        "days_end_of_month_on_the",
    ]
    nb_days: int = 0
    next_month: bool = False


# --------------------------------------------------------------------------- US2 (reconciliation/currency/bank/cash)


class ReconcileWithWriteOff(Payload):
    debit_line_id: int
    credit_line_id: int
    amount: Decimal | None = None
    writeoff_account_id: int | None = None
    writeoff_journal_id: int | None = None


class CurrencyRateCreate(Payload):
    currency_id: int
    rate_date: _dt.date
    rate: Decimal = Field(gt=0)


class RunRevaluation(Payload):
    company_id: int
    as_of: _dt.date


class BankStatementCreate(Payload):
    journal_id: int
    date: _dt.date
    balance_start: Decimal
    balance_end_real: Decimal


class BankStatementLineCreate(Payload):
    statement_id: int
    date: _dt.date
    payment_ref: str | None = None
    partner_id: int | None = None
    amount: Decimal


class StatementLineReconcile(Payload):
    move_line_ids: list[int]


class CashRoundingCreate(Payload):
    name: str = Field(min_length=1, max_length=128)
    rounding: Decimal = Field(gt=0)
    rounding_method: Literal["up", "down", "half_up"]
    strategy: Literal["add_invoice_line", "biggest_tax"]
    account_id: int | None = None


# --------------------------------------------------------------------------- US4 (reports)


class FiscalYearClose(Payload):
    company_id: int
    fiscal_year_end: _dt.date


# --------------------------------------------------------------------------- US5 (debit note / down payment)


class DebitNoteCreate(Payload):
    pass  # empty body


# --------------------------------------------------------------------------- 009-customer-database

# Plain stdlib `re` check, not `EmailStr` — this codebase has no
# `pydantic[email]`/`email-validator` dependency today and FR-013 doesn't
# warrant adding one (Technical Context, research.md).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CustomerCreate(Payload):
    name: str = Field(min_length=1, max_length=256)
    email: str | None = Field(default=None, max_length=256)
    phone: str | None = Field(default=None, max_length=64)
    street: str | None = Field(default=None, max_length=256)
    city: str | None = Field(default=None, max_length=128)
    state_id: int | None = None
    zip: str | None = Field(default=None, max_length=32)
    country_id: int | None = None
    vat: str | None = Field(default=None, max_length=32)
    property_payment_term_id: int | None = None
    property_currency_id: int | None = None

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str | None) -> str | None:
        if v and not _EMAIL_RE.match(v):
            raise ValueError("invalid email format")
        return v


class CustomerUpdate(CustomerCreate):
    name: str | None = Field(default=None, min_length=1, max_length=256)  # optional on update
