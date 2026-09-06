from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, NUMERIC

_RESERVED = frozenset({"id", "create_date", "write_date", "_type"})


class Field:
    def __init__(
        self,
        *,
        string: str = "",
        required: bool = False,
        readonly: bool = False,
        default: Any = None,
    ) -> None:
        self.name: str = ""  # set by BaseModel metaclass
        self.string = string
        self.required = required
        self.readonly = readonly
        self.default = default

    def coerce(self, value: Any) -> Any:
        """Coerce a value from JSON/external source to the Python type asyncpg expects."""
        return value

    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        raise NotImplementedError


class Char(Field):
    def __init__(self, size: int = 255, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.size = size

    @property
    def col_type(self) -> sa.String:
        return sa.String(self.size)

    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        return sa.Column(self.name, sa.String(self.size), nullable=not self.required)


class Integer(Field):
    @property
    def col_type(self) -> sa.Integer:
        return sa.Integer()

    def coerce(self, value: Any) -> Any:
        if value is None:
            return None
        return int(value)

    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        kwargs: dict[str, Any] = {"nullable": not self.required}
        if self.default is not None:
            kwargs["server_default"] = str(int(self.default))
        return sa.Column(self.name, sa.Integer(), **kwargs)


class Boolean(Field):
    def __init__(self, *, default: bool = False, **kwargs: Any) -> None:
        super().__init__(default=default, **kwargs)

    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        return sa.Column(
            self.name,
            sa.Boolean(),
            nullable=False,
            server_default=str(self.default).upper(),
        )


class Float(Field):
    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        kwargs: dict[str, Any] = {"nullable": not self.required}
        if self.default is not None:
            kwargs["server_default"] = str(float(self.default))
        return sa.Column(self.name, sa.Float(), **kwargs)


class Date(Field):
    def coerce(self, value: Any) -> Any:
        if value is None or isinstance(value, datetime.date):
            return value
        return datetime.date.fromisoformat(str(value))

    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        return sa.Column(self.name, sa.Date(), nullable=not self.required)


class Datetime(Field):
    def coerce(self, value: Any) -> Any:
        if value is None or isinstance(value, datetime.datetime):
            return value
        return datetime.datetime.fromisoformat(str(value))

    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        return sa.Column(self.name, sa.DateTime(), nullable=not self.required)


class Text(Field):
    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        return sa.Column(self.name, sa.Text(), nullable=not self.required)


# --- Relational fields ---


class Many2one(Field):
    """FK to another model. Produces an Integer column with a ForeignKey."""

    def __init__(self, relation: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.relation = relation

    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        fk_table = self.relation.replace(".", "_")
        return sa.Column(
            self.name,
            sa.Integer(),
            sa.ForeignKey(f"{fk_table}.id", ondelete="RESTRICT"),
            nullable=not self.required,
        )


class One2many(Field):
    """Virtual field — no DB column. Inverse of a Many2one."""

    def __init__(self, relation: str, relation_field: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.relation = relation
        self.relation_field = relation_field

    def to_sa_column(self) -> None:  # type: ignore[override]
        return None


class Many2many(Field):
    """Virtual field — no DB column. Relationship via a junction table."""

    def __init__(
        self,
        relation: str,
        relation_table: str = "",
        column1: str = "",
        column2: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.relation = relation
        self.relation_table = relation_table
        self.column1 = column1  # FK column pointing to the source model
        self.column2 = column2  # FK column pointing to the target model

    def to_sa_column(self) -> None:  # type: ignore[override]
        return None


# --- Accounting field types ---


class Selection(Field):
    """Enum-like field stored as VARCHAR(64); validated against choices list."""

    def __init__(self, choices: list[tuple[str, str]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.choices = choices  # [(value, label), ...]

    @property
    def valid_values(self) -> list[str]:
        return [v for v, _ in self.choices]

    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        kwargs: dict = {"nullable": not self.required}
        if self.default is not None:
            kwargs["server_default"] = f"'{self.default}'"
        return sa.Column(self.name, sa.String(64), **kwargs)


class Monetary(Field):
    """Monetary amount stored as NUMERIC(20,6); always non-negative; default 0."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("default", Decimal("0"))
        super().__init__(**kwargs)

    def coerce(self, value: Any) -> Any:
        if value is None:
            return Decimal("0")
        return Decimal(str(value))

    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        return sa.Column(
            self.name,
            NUMERIC(precision=20, scale=6),
            nullable=False,
            server_default="0",
        )


class Json(Field):
    """JSON field stored as PostgreSQL JSONB; nullable."""

    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        return sa.Column(self.name, JSONB(), nullable=True)
