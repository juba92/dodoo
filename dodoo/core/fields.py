from __future__ import annotations

from typing import Any

import sqlalchemy as sa

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

    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        return sa.Column(self.name, sa.Integer(), nullable=not self.required)


class Boolean(Field):
    def __init__(self, *, default: bool = False, **kwargs: Any) -> None:
        super().__init__(default=default, **kwargs)

    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        return sa.Column(
            self.name, sa.Boolean(), nullable=False, server_default=str(self.default).upper()
        )


class Float(Field):
    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        return sa.Column(self.name, sa.Float(), nullable=not self.required)


class Date(Field):
    def to_sa_column(self) -> sa.Column:  # type: ignore[type-arg]
        return sa.Column(self.name, sa.Date(), nullable=not self.required)


class Datetime(Field):
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

    def __init__(self, relation: str, relation_table: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.relation = relation
        self.relation_table = relation_table

    def to_sa_column(self) -> None:  # type: ignore[override]
        return None
